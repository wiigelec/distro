"""Qualify the declared bootstrap manifest and freeze host-selected source inputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from dependency_closure import resolve_closure
from host_checks import qualify_execution_host, qualify_source_availability
from host_qualification import installed_arch_packages, parse_arch_version
from preflight import canonical_digest, qualified_baseline
from source_artifacts import SourceError, expected_checksum, read_https, select_component
from upstream_discovery import archive_candidates, fetch_listing, resolve_package

GLIBC_SIGNERS = ('FD19E6D31B192EE4DC63EAD3DC2B16215ED5412A',)
ARCHIVE_EXTENSIONS = ('.tar.xz', '.tar.gz', '.tar.bz2')


def checksum_listing(url: str, filename: str, fetch=read_https) -> tuple[str, str]:
    base = url.rsplit('/', 1)[0] + '/'
    for listing in ('sha256.sum', 'sha512.sum', 'SHA256SUMS', 'SHA512SUMS',
                    'sha256sums', 'sha512sums', 'sha256sums.asc', 'sha512sums.asc'):
        algorithm = 'sha512' if '512' in listing else 'sha256'
        try:
            expected_checksum(fetch(base + listing, limit=2_000_000), filename, algorithm)
            return base + listing, algorithm
        except (OSError, SourceError, ValueError):
            continue
    raise SourceError('no matching upstream checksum entry: ' + filename)


def glibc_release(observed: str, listing=fetch_listing) -> dict:
    pkgver = parse_arch_version(observed)['pkgver']
    match = re.fullmatch(r'(\d+\.\d+)(?:\+r\d+\+g[a-f0-9]{7,40})?', pkgver)
    if not match:
        raise SourceError('glibc host version needs reviewed mapping: ' + pkgver)
    version = match.group(1)
    base = 'https://ftp.gnu.org/gnu/glibc/'
    matches = [record for record in archive_candidates(base, 'glibc', listing(base))
               if record['version'] == version]
    if not matches:
        raise SourceError('upstream glibc release unavailable: ' + version)
    matches.sort(key=lambda item: (ARCHIVE_EXTENSIONS.index(next(
        ext for ext in ARCHIVE_EXTENSIONS if item['filename'].endswith(ext))), item['url']))
    selected = matches[0]
    return {'name': 'glibc', 'version': version, 'artifact_url': selected['url'],
            'filename': selected['filename'], 'mapping_basis': 'host-glibc-release'}


def resolve_sources(manifest: dict, installed: dict[str, str], *, fetch=read_https) -> dict:
    """Map every manifest entry; no extra packages or unreviewed source fallbacks."""
    resolve_closure(manifest)
    documented = dict(manifest)
    entries = []
    for item in manifest['packages']:
        name, host = item['distro_name'], item['host_package']
        if not isinstance(host, str) or host not in installed:
            raise SourceError(name + ': declared host counterpart unavailable: ' + str(host))
        observed = installed[host]
        if name == 'glibc':
            selected = glibc_release(observed)
        else:
            candidate = resolve_package({'distro_name': host,
                                         'host_package_candidate': host,
                                         'host_version_observed': observed})
            if candidate['status'] != 'candidate-exact-match':
                raise SourceError(name + ': upstream release unresolved: ' +
                                  candidate.get('reason', 'unknown'))
            selected = dict(candidate['upstream'])
            selected['mapping_basis'] = candidate['mapping_basis']
        if name == 'gcc' and 'revision' in selected:
            host_version = parse_arch_version(observed)['pkgver']
            release = re.match(r'^(\d+)\.(\d+)\.', host_version)
            if not release:
                raise SourceError('GCC host version needs reviewed source correspondence')
            version = f'{release.group(1)}.{release.group(2)}.0'
            selected = {'name': 'gcc', 'version': version,
                        'filename': f'gcc-{version}.tar.xz',
                        'artifact_url': f'https://gcc.gnu.org/pub/gcc/releases/gcc-{version}/gcc-{version}.tar.xz',
                        'mapping_basis': 'gcc-host-release-train'}
        url = selected['artifact_url']
        filename = selected.get('filename') or url.rsplit('/', 1)[-1]
        if selected.get('patches'):
            raise SourceError(name + ': upstream patch set is not verified')
        if name == 'glibc':
            artifact = {'signature_url': url + '.sig',
                        'signing_fingerprints': list(GLIBC_SIGNERS)}
        else:
            check_url, algorithm = checksum_listing(url, filename, fetch)
            artifact = {'checksum_url': check_url, 'checksum_algorithm': algorithm}
        entries.append({**item, 'upstream': {'name': selected['name'], 'version': selected['version'],
            'official_url': url, 'mapping_basis': selected['mapping_basis'],
            'artifact': {'url': url, 'filename': filename, **artifact}}})
    documented['packages'] = entries
    return documented


def prepare(project: Path, manifest_path: Path) -> dict:
    """Freeze the current declared manifest or reuse its existing verified baseline."""
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes)
    resolve_closure(manifest)
    state = project / '.distro-bootstrap'
    baseline_path = state / 'baseline.json'
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
        if baseline.get('manifest_sha256') != manifest_sha256:
            raise SourceError('bootstrap manifest changed; use a fresh project')
        select_component(baseline, 'gcc')
        if {item['distro_name'] for item in baseline['packages']} != {
                item['distro_name'] for item in manifest['packages']}:
            raise SourceError('frozen package inventory differs from manifest')
        return baseline
    installed = installed_arch_packages()
    resolved = resolve_sources(manifest, installed)
    baseline = qualified_baseline(resolved, installed)
    host = qualify_execution_host()
    available = qualify_source_availability(baseline['packages'])
    baseline.pop('baseline_sha256')
    baseline.update(manifest_sha256=manifest_sha256, host_execution=host,
                    source_availability=available)
    baseline['baseline_sha256'] = canonical_digest(baseline)
    state.mkdir(parents=True, exist_ok=True)
    with baseline_path.open('x', encoding='utf-8') as stream:
        json.dump(baseline, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return baseline
