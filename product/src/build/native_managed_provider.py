"""Authenticated Manage-installed candidate as a production native Build provider.

This authenticates a candidate for construction diagnostics; it NEVER promotes
or labels that candidate as an accepted distro-buildroot collection.
The repository index and installed ownership state must agree with disk bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat

from build.selection import SelectionError
from manage.package import _parse_json, _regular_directory, PackageError
from manage.repository import verify_repository
from manage.install import resolve_candidate, resolve_prerequisites, STATE_DIR, STATE_NAME
from manage.layout import LINKS, canonical_path, canonical_claims


@dataclass(frozen=True)
class ManagedCandidateProvider:
    root: Path
    repository: Path
    identities: tuple[tuple[str, str, str, int], ...]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _authenticate_managed_root(root: Path, repository: Path, *,
                               prerequisite: bool = False) -> ManagedCandidateProvider:
    """Verify installed state, selected closure, and every selected leaf.

    Verification is read-only. Use this gate immediately before construction;
    Build does not write the provider root. This is not an ELF/runtime proof.
    """
    try:
        root = _regular_directory(root)
        repository = _regular_directory(repository)
        if root == repository or root.is_relative_to(repository) or repository.is_relative_to(root):
            raise PackageError('candidate and artifact repository must be independent')
        state_dir = root / STATE_DIR
        if state_dir.is_symlink() or not state_dir.is_dir():
            raise PackageError('unsafe Manage installed-state directory')
        state_path = state_dir / STATE_NAME
        if state_path.is_symlink() or not state_path.is_file():
            raise PackageError('Manage installed-state record missing')
        state = _parse_json(state_path.read_bytes())
        if set(state) != {'schema_version', 'status', 'selection', 'packages'}:
            raise PackageError('unsupported Manage installed-state fields')
        expected_status = ('prerequisites-not-accepted' if prerequisite
                           else 'candidate-not-accepted')
        expected_selection = ('filesystem+linux-headers' if prerequisite
                              else 'distro-buildroot')
        if (state['schema_version'] != 1 or state['status'] != expected_status
                or state['selection'] != expected_selection):
            raise PackageError('not an authenticated Manage-installed FS-004 selection')
        selected = (resolve_prerequisites(repository) if prerequisite
                    else resolve_candidate(repository))
        verify_repository(repository)
        expected = [
            {'identity': rec['identity'], 'relationships': rec['relationships'],
             'artifact': rec['artifact'], 'owned_paths': rec['paths']}
            for rec in selected
        ]
        if state['packages'] != expected:
            raise PackageError('installed-state selection differs from verified repository')
        canonical_claims(list(selected))
        expected_leaves: dict[str, dict] = {}
        declared_directories: dict[str, int] = {}
        for record in selected:
            filesystem = record['identity']['name'] == 'filesystem'
            for entry in record['paths']:
                raw = entry['path']
                name = raw if filesystem and raw in LINKS else canonical_path(raw)
                if entry['type'] == 'directory':
                    declared_directories[name] = entry['mode']
                else:
                    if name in expected_leaves:
                        raise PackageError('duplicate installed leaf')
                    expected_leaves[name] = entry
        # Walk without following aliases or importing host files. Reject
        # unowned files/symlinks, including in implicit ancestor directories.
        encountered_leaves: set[str] = set()
        directories: set[str] = set()
        for base, children, files in os.walk(root, topdown=True, followlinks=False):
            base_path = Path(base)
            for name in list(children) + list(files):
                path = base_path / name
                rel = path.relative_to(root).as_posix()
                if rel == STATE_DIR:
                    if path.is_symlink() or not path.is_dir():
                        raise PackageError('unsafe installed-state directory')
                    children.remove(name)
                    continue
                info = path.lstat()
                if stat.S_ISDIR(info.st_mode):
                    directories.add(rel)
                elif stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    if rel not in expected_leaves:
                        raise PackageError(f'unowned installed file or link: {rel}')
                    entry = expected_leaves[rel]
                    if entry['type'] == 'file':
                        if not stat.S_ISREG(info.st_mode) or (info.st_size != entry['size']
                                or stat.S_IMODE(info.st_mode) != entry['mode']
                                or _hash_file(path) != entry['sha256']):
                            raise PackageError(f'installed file differs from selected artifact: {rel}')
                    elif entry['type'] == 'symlink':
                        if not stat.S_ISLNK(info.st_mode) or os.readlink(path) != entry['target']:
                            raise PackageError(f'installed symlink differs from selected artifact: {rel}')
                    else:
                        raise PackageError('invalid installed leaf type')
                    encountered_leaves.add(rel)
                else:
                    raise PackageError(f'unsupported installed special file: {rel}')
        if encountered_leaves != set(expected_leaves):
            raise PackageError('missing installed package payload')
        if not set(declared_directories).issubset(directories):
            raise PackageError('selected installed directories missing')
        for name in directories:
            path = root / name
            mode = declared_directories.get(name, 0o755)
            if stat.S_IMODE(path.lstat().st_mode) != mode:
                raise PackageError(f'installed directory mode differs from selection: {name}')
        state_dir = root / STATE_DIR
        if stat.S_IMODE(state_dir.lstat().st_mode) != 0o700:
            raise PackageError('incorrect installed-state directory mode')
        # The state itself may not conceal additional records.
        if {p.name for p in state_dir.iterdir()} != {STATE_NAME}:
            raise PackageError('unexpected installed-state entry')
        if stat.S_IMODE(state_path.stat().st_mode) & 0o022:
            raise PackageError('installed state is writable by group/others')
        identities = tuple((r['identity']['name'], r['identity']['version'],
                            r['identity']['architecture'], r['identity']['revision'])
                           for r in selected)
        return ManagedCandidateProvider(root, repository, identities)
    except (PackageError, OSError, ValueError, TypeError, KeyError) as exc:
        raise SelectionError(f'Manage-installed provider authentication failed: {exc}') from exc

def authenticate_managed_candidate(root: Path, repository: Path) -> ManagedCandidateProvider:
    """Authenticate an installed, complete but unaccepted collection candidate."""
    return _authenticate_managed_root(root, repository)

def authenticate_managed_prerequisites(root: Path, repository: Path) -> ManagedCandidateProvider:
    """Authenticate Manage-installed filesystem and Linux headers only.

    This root is not an executable buildroot. Only its verified header tree
    may be mounted into the authenticated Stage 1B bootstrap executor.
    """
    return _authenticate_managed_root(root, repository, prerequisite=True)
