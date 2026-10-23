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



def fetch_json(url):
    """Fetch a repository commit/tag identity from a public HTTPS API."""
    if urlparse(url).scheme != 'https':
        raise ValueError('HTTPS repository endpoint required')
    request = Request(url, headers={'User-Agent': 'Distro-bootstrap-source-discovery/1',
                                    'Accept': 'application/vnd.github+json'})
    with urlopen(request, timeout=40) as response:
        if urlparse(response.geturl()).scheme != 'https':
            raise ValueError('repository API redirected to insecure transport')
        return json.load(response)


def source_candidate(name, version, url, basis, **extra):
    return {'status': 'candidate-exact-match',
            'mapping_basis': basis,
            'upstream': {'name': name, 'version': version,
                         'artifact_url': url, **extra}}


def resolve_special(name, candidate, listing, api):
    """Handle upstream layouts not represented by a single GNU release archive."""
    if name == 'linux':
        match = re.fullmatch(r'(\d+\.\d+\.\d+)\.arch\d+', candidate)
        if not match:
            return None
        version = match.group(1)
        major = version.split('.')[0]
        base = f'https://cdn.kernel.org/pub/linux/kernel/v{major}.x/'
        matches = [x for x in archive_candidates(base, 'linux', listing(base))
                   if x['version'] == version]
        if matches:
            return source_candidate(name, version, matches[0]['url'],
                                    'arch-kernel-suffix-to-upstream-release',
                                    filename=matches[0]['filename'])
        return None
    if name == 'bash':
        match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', candidate)
        if not match:
            return None
        major, minor, patch = match.groups()
        count = int(patch)
        if count == 0 or count > 999:
            return None
        version = major + '.' + minor
        base = GNU + 'bash/'
        archives = [x for x in archive_candidates(base, 'bash', listing(base))
                    if x['version'] == version]
        if not archives:
            return None
        archives.sort(key=lambda x: ARCHIVE_EXTENSIONS.index(next(
            ext for ext in ARCHIVE_EXTENSIONS if x['filename'].endswith(ext))))
        patch_base = base + f'bash-{version}-patches/'
        found = {unquote(urlparse(urljoin(patch_base, link)).path.rsplit('/', 1)[-1]):
                 urljoin(patch_base, link) for link in listing(patch_base)}
        patch_urls = []
        for index in range(1, count + 1):
            filename = f'bash{major}{minor}-{index:03d}'
            url = found.get(filename)
            if not url or urlparse(url).netloc != urlparse(patch_base).netloc:
                return None
            patch_urls.append(url)
        return source_candidate(name, candidate, archives[0]['url'],
                                'upstream-base-plus-sequential-patches',
                                filename=archives[0]['filename'], patches=patch_urls,
                                base_version=version)
    if name == 'gcc':
        match = re.fullmatch(r'\d+\.\d+\.\d+\+r\d+\+g([a-f0-9]{7,40})', candidate)
        if not match:
            return None
        short_sha = match.group(1)
        data = api(f'https://api.github.com/repos/gcc-mirror/gcc/commits/{short_sha}')
        sha = data.get('sha')
        if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{40}', sha) or not sha.startswith(short_sha):
            return None
        return source_candidate(name, sha,
                                f'https://github.com/gcc-mirror/gcc/archive/{sha}.tar.gz',
                                'arch-vcs-revision-to-gcc-mirror-commit',
                                revision=sha, reference='gcc-mirror/gcc')
    if name == 'grub':
        if not VERSION.fullmatch(candidate):
            return None
        tag = 'grub-' + candidate
        project = 'gnu-grub%2Fgrub'
        data = api(f'https://gitlab.freedesktop.org/api/v4/projects/{project}/repository/tags/{tag}')
        commit = data.get('commit', {})
        revision = commit.get('id')
        if data.get('name') != tag or not isinstance(revision, str) or not re.fullmatch('[a-f0-9]{40}', revision):
            return None
        filename = f'grub-{tag}.tar.gz'
        return source_candidate(name, candidate,
                                f'https://gitlab.freedesktop.org/gnu-grub/grub/-/archive/{tag}/{filename}',
                                'upstream-gitlab-release-tag', tag=tag,
                                revision=revision, filename=filename,
                                reference='gnu-grub/grub')
    if name == 'systemd':
        repo = 'systemd/systemd'
        tag = 'v' + candidate
        data = api(f'https://api.github.com/repos/{repo}/git/ref/tags/{tag}')
        obj = data.get('object', {})
        if obj.get('type') not in ('tag', 'commit') or not re.fullmatch('[a-f0-9]{40}', obj.get('sha', '')):
            return None
        return source_candidate(name, candidate,
                                f'https://github.com/{repo}/archive/refs/tags/{tag}.tar.gz',
                                'upstream-repository-release-tag', tag=tag, reference=repo)
    return None

def resolve_package(record, listing=fetch_listing, api=fetch_json):
    name = record['distro_name']
    observed = record.get('host_version_observed')
    output = {'distro_name': name, 'host_package': record.get('host_package_candidate'),
              'host_version': observed, 'status': 'unresolved'}
    if not observed:
        output['reason'] = 'host-counterpart-missing'
        return output
    candidate = arch_pkgver(observed)
    output['host_pkgver_candidate'] = candidate
    if name in ('bash', 'gcc', 'grub', 'linux', 'systemd'):
        try:
            special = resolve_special(name, candidate, listing, api)
        except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
            output['reason'] = 'upstream-discovery-failed'
            output['diagnostic'] = str(exc)[:240]
            return output
        if special is not None:
            output.update(special)
            return output
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


def discover_from_audit(audit, listing=fetch_listing, api=fetch_json):
    if (audit.get('schema_version') != 1 or audit.get('host_kind') != 'arch'
            or not isinstance(audit.get('packages'), list)):
        raise ValueError('invalid Arch host-audit report')
    packages = [resolve_package(record, listing, api) for record in audit['packages']]
    return {'schema_version': 1, 'status': 'unreviewed-source-discovery',
            'host_kind': 'arch', 'manifest_sha256': audit.get('manifest_sha256'),
            'packages': packages,
            'summary': {'matched': sum(p['status'] == 'candidate-exact-match' for p in packages),
                        'unresolved': sum(p['status'] != 'candidate-exact-match' for p in packages)},
            'note': 'Only candidates: source authenticity, package correspondences and dependency closure still require qualification.'}
