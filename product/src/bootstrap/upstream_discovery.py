"""Discover upstream release candidates corresponding to an observed Arch host.

The result is evidence for preflight review, never a qualified mapping or source lock.
Only exact upstream release identifiers are selected automatically. Distribution
patchlevels, VCS snapshots and unknown naming rules remain unresolved.
"""
from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import Request, urlopen

# Provider locations, not a pinned version catalog. Release selection is host-led.
GNU = "https://ftp.gnu.org/gnu/"
PROVIDERS = {
    **{name: (GNU + name + '/', name) for name in (
        'bash', 'coreutils', 'diffutils', 'gawk', 'grep', 'make',
        'sed', 'tar', 'grub')},
    'binutils': ('https://sourceware.org/pub/binutils/releases/', 'binutils'),
}
ARCHIVE_EXTENSIONS = ('.tar.xz', '.tar.gz', '.tar.bz2')
VERSION = re.compile(r'^[0-9]+(?:\.[0-9]+)+(?:[a-z][0-9]*)?$')


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.extend(value for key, value in attrs if key == 'href' and value)


def arch_pkgver(observed):
    """Keep the complete version in evidence, returning only a candidate upstream key."""
    if not isinstance(observed, str) or '-' not in observed:
        raise ValueError('invalid Arch version')
    stem, release = observed.rsplit('-', 1)
    if not release:
        raise ValueError('invalid Arch release')
    return stem.split(':', 1)[-1]


def fetch_listing(url):
    if urlparse(url).scheme != 'https':
        raise ValueError('HTTPS upstream listing required')
    request = Request(url, headers={'User-Agent': 'Distro-bootstrap-source-discovery/1'})
    with urlopen(request, timeout=40) as response:
        if urlparse(response.geturl()).scheme != 'https':
            raise ValueError('upstream redirected to insecure transport')
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError('upstream directory listing too large')
    parser = Links()
    parser.feed(data.decode('utf-8', errors='replace'))
    return parser.links


def archive_candidates(base, name, links):
    """Adapt the prototype g1-chroot archive enumeration, with no latest selection."""
    found = []
    for link in links:
        target = urljoin(base, link)
        if urlparse(target).scheme != 'https' or urlparse(target).netloc != urlparse(base).netloc:
            continue
        filename = unquote(urlparse(target).path.rsplit('/', 1)[-1])
        ext = next((x for x in ARCHIVE_EXTENSIONS if filename.endswith(x)), None)
        if ext is None or not filename.startswith(name + '-'):
            continue
        version = filename[len(name) + 1:-len(ext)]
        if VERSION.fullmatch(version):
            found.append({'version': version, 'url': target, 'filename': filename})
    return found


def resolve_package(record, listing=fetch_listing):
    name = record['distro_name']
    observed = record.get('host_version_observed')
    output = {'distro_name': name, 'host_package': record.get('host_package_candidate'),
              'host_version': observed, 'status': 'unresolved'}
    if not observed:
        output['reason'] = 'host-counterpart-missing'
        return output
    candidate = arch_pkgver(observed)
    output['host_pkgver_candidate'] = candidate
    if not VERSION.fullmatch(candidate):
        output['reason'] = 'host-version-needs-package-specific-mapping'
        return output
    provider = PROVIDERS.get(name)
    if provider is None:
        output['reason'] = 'upstream-provider-not-configured'
        return output
    base, archive_name = provider
    output['discovery_url'] = base
    try:
        matches = [x for x in archive_candidates(base, archive_name, listing(base))
                   if x['version'] == candidate]
    except (OSError, ValueError, UnicodeError) as exc:
        output['reason'] = 'upstream-discovery-failed'
        output['diagnostic'] = str(exc)[:240]
        return output
    if not matches:
        output['reason'] = 'no-exact-upstream-release'
        return output
    # Archive format preference is deterministic and recorded, not a version guess.
    matches.sort(key=lambda x: (ARCHIVE_EXTENSIONS.index(next(
        e for e in ARCHIVE_EXTENSIONS if x['filename'].endswith(e))), x['url']))
    selected = matches[0]
    output.update(status='candidate-exact-match', upstream={'name': archive_name,
                  'version': candidate, 'artifact_url': selected['url'],
                  'filename': selected['filename']}, mapping_basis='exact-host-pkgver-and-upstream-archive')
    return output


def discover_from_audit(audit, listing=fetch_listing):
    if (audit.get('schema_version') != 1 or audit.get('host_kind') != 'arch'
            or not isinstance(audit.get('packages'), list)):
        raise ValueError('invalid Arch host-audit report')
    packages = [resolve_package(record, listing) for record in audit['packages']]
    return {'schema_version': 1, 'status': 'unreviewed-source-discovery',
            'host_kind': 'arch', 'manifest_sha256': audit.get('manifest_sha256'),
            'packages': packages,
            'summary': {'matched': sum(p['status'] == 'candidate-exact-match' for p in packages),
                        'unresolved': sum(p['status'] != 'candidate-exact-match' for p in packages)},
            'note': 'Only candidates: source authenticity, package correspondences and dependency closure still require qualification.'}
