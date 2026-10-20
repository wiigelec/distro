"""Verify official-source checksums and freeze consumed artifacts per execution.

The source identity always originates in the previously qualified host baseline.
No implicit package-version discovery, mirror substitution, or lock rewriting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class SourceError(ValueError):
    """An upstream source does not match its frozen qualified identity."""


def canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def https_url(value: str) -> str:
    if not isinstance(value, str):
        raise SourceError('source URL is missing')
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise SourceError('source URL must be an absolute HTTPS URL without credentials or fragment')
    return value


def read_https(url: str, *, limit: int) -> bytes:
    https_url(url)
    with urlopen(Request(url, headers={'User-Agent': 'Distro-source-acquisition/1'}), timeout=60) as stream:
        # urllib follows redirects. Reject HTTP downgrade or a non-HTTPS final URL.
        https_url(stream.geturl())
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise SourceError('source resource exceeds configured size limit')
        return data


def expected_checksum(index: bytes, filename: str, algorithm: str) -> str:
    if algorithm not in ('sha256', 'sha512'):
        raise SourceError('unsupported official checksum algorithm')
    if '/' in filename or '\\' in filename or filename in ('', '.', '..'):
        raise SourceError('invalid source archive filename')
    try:
        lines = index.decode('utf-8').splitlines()
    except UnicodeDecodeError as exc:
        raise SourceError('checksum listing is not UTF-8') from exc
    pattern = re.compile(r'[0-9a-fA-F]{' + str(hashlib.new(algorithm).digest_size * 2) + r'}')
    digests = []
    for line in lines:
        fields = line.split()
        if len(fields) == 2 and pattern.fullmatch(fields[0]):
            recorded = fields[1].lstrip('*').removeprefix('./')
            if recorded == filename:
                digests.append(fields[0].lower())
    if len(digests) != 1:
        raise SourceError('official checksum listing lacks one unambiguous archive entry')
    return digests[0]


def select_component(baseline: dict, package_name: str) -> tuple[dict, dict]:
    if not isinstance(baseline, dict) or baseline.get('status') != 'qualified-mapping-baseline':
        raise SourceError('qualified source baseline required')
    fingerprint = baseline.get('baseline_sha256')
    payload = dict(baseline)
    payload.pop('baseline_sha256', None)
    if fingerprint != canonical_digest(payload):
        raise SourceError('qualified baseline checksum differs from its content')
    selected = [p for p in baseline['packages'] if p.get('distro_name') == package_name]
    if len(selected) != 1:
        raise SourceError('selected package absent or ambiguous in qualified baseline')
    return selected[0], selected[0]['upstream']


def source_spec(upstream: dict) -> dict:
    """Resolve the reviewed artifact location and official checksum method.

    Signature-bearing sources are deliberately rejected until trusted-key
    verification is implemented; an unsigned checksum is not a downgrade path.
    """
    if 'signature_url' in upstream or 'signing_fingerprints' in upstream:
        raise SourceError('detached-signature verification not yet available; refusing checksum downgrade')
    artifact = upstream.get('artifact')
    if not isinstance(artifact, dict):
        raise SourceError('reviewed upstream artifact specification missing')
    url = https_url(artifact.get('url'))
    listing = https_url(artifact.get('checksum_url'))
    filename = artifact.get('filename')
    algorithm = artifact.get('checksum_algorithm')
    if not isinstance(filename, str) or not filename or '/' in filename or '\\' in filename:
        raise SourceError('invalid reviewed source filename')
    if algorithm not in ('sha256', 'sha512'):
        raise SourceError('unsupported official source checksum algorithm')
    if urlparse(url).path.rsplit('/', 1)[-1] != filename:
        raise SourceError('reviewed source filename and URL disagree')
    return {'url': url, 'checksum_url': listing, 'filename': filename,
            'checksum_algorithm': algorithm}


def write_once(path: Path, content: bytes) -> None:
    """Durably publish complete bytes without ever replacing another file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, prefix='.source-',
                                         delete=False) as stream:
            temp_name = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp_name, path)  # Atomic no-overwrite publication.
        folder_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(folder_fd)
        finally:
            os.close(folder_fd)
    except FileExistsError as exc:
        raise SourceError(f'existing source or lock cannot be replaced: {path.name}') from exc
    finally:
        if temp_name is not None:
            os.unlink(temp_name)


def verify_and_lock(baseline: dict, name: str, cache: Path, lock_dir: Path,
                    *, recipe_sha256: str, offline: bool = False,
                    fetch=read_https) -> dict:
    """Verify cached or fetched source and create immutable first-use lock.

    Existing locks are rechecked against the unchanged baseline and exact
    archived bytes. Missing cache bytes never trigger silent source reselection.
    """
    component, upstream = select_component(baseline, name)
    spec = source_spec(upstream)
    if not re.fullmatch('[0-9a-f]{64}', recipe_sha256):
        raise SourceError('recipe identity must be SHA-256')
    if not name or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.-]*', name):
        raise SourceError('invalid package identity for lock path')
    identity = {'baseline_sha256': baseline['baseline_sha256'],
                'host_package': component['host_package'], 'host_version': component['host_version'],
                'distro_name': name, 'upstream': upstream, 'recipe_sha256': recipe_sha256,
                'source': spec}
    lock_path = lock_dir / (name + '.json')
    archive_path = cache / (name + '-' + spec['filename'])
    if lock_path.exists():
        try:
            locked = json.loads(lock_path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise SourceError('source lock cannot be decoded') from exc
        if locked.get('identity') != identity:
            raise SourceError('source lock conflicts with fixed baseline or recipe input')
        if not archive_path.is_file():
            raise SourceError('locked source archive missing; cannot resume')
        digest = file_hash(archive_path, locked['checksum_algorithm'])
        if digest != locked.get('digest'):
            raise SourceError('locked source bytes changed')
        return locked
    if offline:
        raise SourceError('offline source consumption requires existing verified lock')
    index = fetch(spec['checksum_url'], limit=2_000_000)
    expected = expected_checksum(index, spec['filename'], spec['checksum_algorithm'])
    data = fetch(spec['url'], limit=2_000_000_000)
    actual = hashlib.new(spec['checksum_algorithm'], data).hexdigest()
    if actual != expected:
        raise SourceError('source archive does not match official checksum')
    write_once(archive_path, data)
    locked = {'schema_version': 1, 'identity': identity, 'digest': actual,
              'checksum_algorithm': spec['checksum_algorithm'], 'verification': 'official-https-checksum'}
    write_once(lock_path, (json.dumps(locked, indent=2, sort_keys=True) + '\n').encode())
    return locked


def file_hash(path: Path, algorithm: str) -> str:
    if algorithm not in ('sha256', 'sha512'):
        raise SourceError('unknown locked checksum algorithm')
    digest = hashlib.new(algorithm)
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Verify and lock an upstream source archive')
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--package', required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--locks', type=Path, required=True)
    parser.add_argument('--recipe-sha256', required=True)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args(argv)
    try:
        if os.geteuid() == 0:
            raise SourceError('run as an unprivileged user')
        baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
        lock = verify_and_lock(baseline, args.package, args.cache, args.locks,
                               recipe_sha256=args.recipe_sha256, offline=args.offline)
        print(json.dumps(lock, sort_keys=True))
        return 0
    except (SourceError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f'Source acquisition blocked: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
