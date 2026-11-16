"""FS-004 pinned Stage 1C source selection, without activation of native Build.

This selection is intentionally distinct from the accepted FS-003 Sed-only
executable list. Package recipes/manifests must be migrated and reviewed before
this catalog is consumed by the native Build controller.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from build.selection import SelectionError, _yaml, _keys, _name, _version, _DIGEST

@dataclass(frozen=True)
class NativePackageSelection:
    name: str
    version: str
    checksum: str | None
    kind: str

# Planning-selected payload identities; not a claim of successful closure.
VERSIONS = {
    'filesystem': '1', 'bash': '5.3', 'coreutils': '9.10', 'sed': '4.10',
    'grep': '3.12', 'gawk': '5.4.0', 'make': '4.4.1',
    'diffutils': '3.12', 'tar': '1.35', 'binutils': '2.47',
    'gcc': '16.2.0', 'linux': '7.1.8', 'glibc': '2.44',
}

def load_native_catalog(path: Path) -> tuple[NativePackageSelection, ...]:
    d = _yaml(path)
    _keys(d, {'packages'})
    raw = d['packages']
    if not isinstance(raw, list) or len(raw) != len(VERSIONS):
        raise SelectionError('native catalog must select exactly thirteen payload identities')
    found = {}
    for item in raw:
        if not isinstance(item, dict):
            raise SelectionError('native package selection must be a mapping')
        _keys(item, {'name', 'version', 'kind'}, {'checksum'})
        name, version, kind = item['name'], item['version'], item['kind']
        if not _name(name) or not _version(version) or name in found or VERSIONS.get(name) != version:
            raise SelectionError('unknown, duplicate, or conflicting native package selection')
        if name == 'filesystem':
            if kind != 'local' or 'checksum' in item:
                raise SelectionError('filesystem must be repository-maintained local source')
            checksum = None
        else:
            checksum = item.get('checksum')
            if kind != 'upstream' or not isinstance(checksum, str) or not _DIGEST.fullmatch(checksum):
                raise SelectionError('native upstream package requires fixed source SHA-256')
            checksum = checksum.lower()
        found[name] = NativePackageSelection(name, version, checksum, kind)
    if set(found) != set(VERSIONS):
        raise SelectionError('incomplete native catalog')
    return tuple(found[name] for name in VERSIONS)
