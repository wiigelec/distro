"""Resolve installed host sources into an immutable construction baseline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from host_qualification import installed_arch_packages, parse_arch_version
from source_artifacts import (SourceError, canonical_digest, expected_checksum,
                              read_https)
from upstream_discovery import archive_candidates, fetch_listing

SOURCE_OWNERS = ('binutils', 'gcc', 'linux-api-headers', 'glibc')


def locate_checksum(url: str, filename: str, fetch=read_https) -> tuple[str, str]:
    """Locate an unambiguous upstream checksum entry; never invent a digest."""
    base = url.rsplit('/', 1)[0] + '/'
    candidates = ('sha256.sum', 'sha512.sum', 'SHA256SUMS', 'SHA512SUMS',
                  'sha256sums', 'sha512sums', 'sha256sums.asc', 'sha512sums.asc')
    errors = []
    for index in candidates:
        algorithm = 'sha512' if '512' in index else 'sha256'
        address = base + index
        try:
            contents = fetch(address, limit=2_000_000)
            expected_checksum(contents, filename, algorithm)
            return address, algorithm
        except (OSError, SourceError, ValueError) as exc:
            errors.append(index + ': ' + str(exc)[:80])
    raise SourceError('no authenticated upstream checksum listing for ' + filename +
                      '; checked ' + ', '.join(candidates))


def make_baseline(audit: dict, manifest: dict, fetch=read_https) -> dict:
    """Preserve source selections and their verification methods for this run."""
    found = {entry['distro_name']: entry for entry in audit['packages']}
    selected = {entry['distro_name'] for entry in manifest['packages']}
    result = []
    for owner in SOURCE_OWNERS:
        alias = 'linux' if owner == 'linux-api-headers' else owner
        record = found.get(alias)
        if record is None:
            raise SourceError('host package is not available: ' + alias)
        candidate = record.get('upstream_discovery', {})
        if candidate.get('status') != 'candidate-exact-match':
            raise SourceError('no upstream source for ' + alias + ': ' +
                              candidate.get('reason', 'unresolved'))
        upstream = candidate['upstream']
        # GCC's installed snapshot is referenced by its release train for
        # construction, as in the bootstrap prototype's release policy.
        if owner == 'gcc' and 'revision' in upstream:
            match = re.match(r'^(\d+)\.(\d+)\.', record['host_version_observed'])
            if not match:
                raise SourceError('unrecognized installed GCC release train')
            version = f'{match.group(1)}.{match.group(2)}.0'
            upstream = {'name': 'gcc', 'version': version,
                        'filename': f'gcc-{version}.tar.xz',
                        'artifact_url': (f'https://gcc.gnu.org/pub/gcc/releases/'
                                         f'gcc-{version}/gcc-{version}.tar.xz')}
            candidate = dict(candidate, mapping_basis='gcc-release-train-base')
        url = upstream['artifact_url']
        filename = upstream.get('filename') or url.rsplit('/', 1)[-1]
        if upstream.get('patches'):
            raise SourceError(alias + ': patch-bearing source needs verified patch acquisition')
        checksum_url, algorithm = locate_checksum(url, filename, fetch)
        host_name = record['host_package_candidate']
        version = record['host_version_observed']
        result.append({'distro_name': owner, 'host_package': host_name,
                       'host_version': parse_arch_version(version),
                       'upstream': {'name': upstream['name'], 'version': upstream['version'],
                                    'official_url': url, 'mapping_basis': candidate['mapping_basis'],
                                    'artifact': {'url': url, 'filename': filename,
                                                 'checksum_url': checksum_url,
                                                 'checksum_algorithm': algorithm}}})
    output = {'schema_version': 1, 'host_kind': 'arch',
              'status': 'qualified-mapping-baseline',
              'manifest_sha256': audit['manifest_sha256'],
              'packages': sorted(result, key=lambda r: r['distro_name'])}
    output['baseline_sha256'] = canonical_digest(output)
    return output


def save_once(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(data, sort_keys=True, indent=2) + '\n').encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise SourceError('existing execution baseline differs; start a new project')
        return
    with path.open('xb') as file:
        file.write(raw)


def prepare(project: Path, manifest_path: Path, audit_function) -> dict:
    """Read existing execution inputs or discover and freeze a new selection."""
    state = project / '.distro-bootstrap'
    baseline_path = state / 'baseline.json'
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())
        digest = baseline.get('baseline_sha256')
        payload = dict(baseline)
        payload.pop('baseline_sha256', None)
        if digest != canonical_digest(payload):
            raise SourceError('saved execution baseline has changed')
        print('[build] resuming existing source baseline', flush=True)
        return baseline
    print('[build] auditing installed host packages', flush=True)
    manifest = json.loads(manifest_path.read_text())
    audit = audit_function(manifest_path)
    if audit['source_summary']['unresolved']:
        missing = [p['distro_name'] for p in audit['packages']
                   if p.get('upstream_discovery', {}).get('status') != 'candidate-exact-match']
        raise SourceError('upstream discovery unresolved: ' + ', '.join(missing))
    # The C library is an independent compiler input even if the selected
    # native package inventory does not yet include it.
    if not any(item['distro_name'] == 'glibc' for item in audit['packages']):
        installed = installed_arch_packages()
        version = installed.get('glibc')
        if not version:
            raise SourceError('installed glibc is required for the C runtime')
        pkgver = parse_arch_version(version)['pkgver']
        release = re.fullmatch(r'(\d+\.\d+)(?:\+r\d+\+g[a-f0-9]{7,40})?', pkgver)
        if not release:
            raise SourceError('unsupported installed glibc source version: ' + pkgver)
        upstream_version = release.group(1)
        base = 'https://sourceware.org/pub/glibc/releases/'
        matches = [candidate for candidate in archive_candidates(
            base, 'glibc', fetch_listing(base)) if candidate['version'] == upstream_version]
        if not matches:
            raise SourceError('upstream glibc archive missing for ' + upstream_version)
        matches.sort(key=lambda x: (('.tar.xz', '.tar.gz', '.tar.bz2').index(
            next(ext for ext in ('.tar.xz', '.tar.gz', '.tar.bz2')
                 if x['filename'].endswith(ext))), x['url']))
        selected = matches[0]
        audit['packages'].append({'distro_name': 'glibc',
            'host_package_candidate': 'glibc', 'host_version_observed': version,
            'upstream_discovery': {'status': 'candidate-exact-match',
                'mapping_basis': ('glibc-release-train-base' if pkgver != upstream_version
                                  else 'exact-host-pkgver-and-upstream-archive'),
                'upstream': {'name': 'glibc', 'version': upstream_version,
                             'artifact_url': selected['url'],
                             'filename': selected['filename']}}})
    print('[build] locating official source checksums', flush=True)
    baseline = make_baseline(audit, manifest)
    state.mkdir(parents=True, exist_ok=True)
    save_once(state / 'host-audit.json', audit)
    save_once(baseline_path, baseline)
    return baseline
