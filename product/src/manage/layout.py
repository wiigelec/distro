"""FS-004 merged-/usr layout and canonical package ownership authority.

The filesystem package owns aliases. Consumers resolve approved aliases to
canonical paths; no arbitrary filesystem link may become an install ancestor.
This module neither constructs roots nor publishes collection completion.
"""
from __future__ import annotations

from manage.package import PackageError

# Exact selected filesystem package links (target relative to link parent).
LINKS = {
    'bin': ('usr/bin', 'usr/bin'),
    'sbin': ('usr/bin', 'usr/bin'),
    'lib': ('usr/lib', 'usr/lib'),
    'lib64': ('usr/lib', 'usr/lib'),
    'usr/sbin': ('bin', 'usr/bin'),
    'usr/lib64': ('lib', 'usr/lib'),
}
DIRECTORIES = {
    'etc': 0o755, 'usr': 0o755, 'usr/bin': 0o755,
    'usr/lib': 0o755, 'usr/include': 0o755,
    'usr/share': 0o755, 'var': 0o755,
    'var/lib': 0o755, 'var/cache': 0o755,
    'var/log': 0o755, 'var/tmp': 0o1777,
    'tmp': 0o1777, 'run': 0o755, 'dev': 0o755,
    'proc': 0o555, 'sys': 0o555,
}


def canonical_path(path: str) -> str:
    """Expand only the six reviewed merged-/usr aliases, without host IO."""
    current = path
    for _ in range(4):
        match = next((name for name in sorted(LINKS, key=lambda x: (-len(x), x))
                      if current == name or current.startswith(name + '/')), None)
        if match is None:
            return current
        suffix = current[len(match):]
        current = LINKS[match][1] + suffix
    raise PackageError(f'cyclic or excessive canonical path alias: {path}')


def _filesystem(records: list[dict]) -> dict | None:
    selected = [r for r in records if r['identity']['name'] == 'filesystem']
    if not selected:
        return None  # Legacy FS-003 repositories need no filesystem package.
    if len(selected) != 1 or selected[0]['identity']['version'] != '1':
        raise PackageError('ambiguous or incorrect selected filesystem package')
    fs = selected[0]
    paths = {p['path']: p for p in fs['paths']}
    if set(paths) != set(DIRECTORIES) | set(LINKS):
        raise PackageError('filesystem package does not own exact selected layout')
    for name, mode in DIRECTORIES.items():
        if paths[name] != {'path': name, 'type': 'directory', 'mode': mode}:
            raise PackageError(f'filesystem directory identity mismatch: {name}')
    for name, (target, _canonical) in LINKS.items():
        record = paths[name]
        if (record.get('type') != 'symlink' or record.get('target') != target or
                set(record) != {'path','type','mode','target'}):
            raise PackageError(f'filesystem link identity mismatch: {name}')
    if fs['relationships']:
        raise PackageError('filesystem package must have no install dependencies')
    return fs


def canonical_claims(records: list[dict]) -> tuple[dict[str, int], dict[str, tuple]]:
    """Preflight entire candidate: exact layout, canonical leaves and modes.

    Directory sharing requires identical modes. A file/link owns one canonical
    leaf, including when a package spells that path through a selected alias.
    No leaf may be another installed member's ancestor.
    """
    fs = _filesystem(records)
    modes: dict[str, int] = {}
    leaves: dict[str, tuple] = {}
    for record in records:
        identity = record['identity']
        key = (identity['name'], identity['version'],
               identity['architecture'], identity['revision'])
        for entry in record['paths']:
            raw = entry['path']
            if raw == '.distro' or raw.startswith('.distro/'):
                raise PackageError('reserved installed state path in package')
            # The owner of the six alias nodes retains their literal paths.
            alias_node = fs is record and raw in LINKS
            path = raw if alias_node else canonical_path(raw) if fs else raw
            if entry['type'] == 'directory':
                if path in leaves or (path in modes and modes[path] != entry['mode']):
                    raise PackageError(f'incompatible directory ownership: {path}')
                modes[path] = entry['mode']
            else:
                if path in leaves or path in modes:
                    raise PackageError(f'duplicate canonical leaf ownership: {path}')
                leaves[path] = key
    for path in set(modes) | set(leaves):
        parts = path.split('/')
        for n in range(1, len(parts)):
            ancestor = '/'.join(parts[:n])
            if ancestor in leaves:
                raise PackageError(f'non-directory canonical ancestor: {ancestor}')
    return modes, leaves
