"""cross-toolchain installed-file ownership evidence for FS-002.

Post-install comparison only detects changes; it cannot prevent an in-place
DESTDIR overwrite. cross-chroot execution remains disabled until safe staging and
pre-merge collision checking plus justified ownership transitions are designed.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat


class OwnershipError(RuntimeError):
    """An imported filesystem entry was changed or cannot be inventoried."""


def snapshot_imported_root(root: Path) -> dict[str, tuple[str, int, str]]:
    """Hash all imported files and record directories/links without dereferencing."""
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir() or root.resolve() != root:
        raise OwnershipError("import root must be a real directory")
    result: dict[str, tuple[str, int, str]] = {}
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as children:
            for entry in children:
                path = Path(entry.path)
                name = path.relative_to(root).as_posix()
                info = entry.stat(follow_symlinks=False)
                mode = stat.S_IMODE(info.st_mode)
                if stat.S_ISDIR(info.st_mode):
                    result[name] = ("dir", mode, "")
                    pending.append(path)
                elif stat.S_ISLNK(info.st_mode):
                    result[name] = ("link", mode, os.readlink(path))
                elif stat.S_ISREG(info.st_mode):
                    sha = hashlib.sha256()
                    with path.open("rb") as source:
                        for block in iter(lambda: source.read(1024 * 1024), b""):
                            sha.update(block)
                    result[name] = ("file", mode, sha.hexdigest())
                else:
                    raise OwnershipError(f"unsupported imported entry: {name}")
    return result


def require_preserved_imports(root: Path, baseline: dict[str, tuple[str, int, str]]) -> None:
    """Fail if any imported entry changed; additions alone are not collisions.

    This is an evidence check, not permission for in-place installation.
    """
    if not isinstance(baseline, dict):
        raise OwnershipError("invalid imported-file baseline")
    current = snapshot_imported_root(root)
    for path, identity in baseline.items():
        if current.get(path) != identity:
            raise OwnershipError(f"imported filesystem entry changed or missing: {path}")


def check_staged_install(installed: Path, staged: Path) -> dict[str, tuple[str, int, str]]:
    """Reject a staged installation that would overwrite any existing entry.

    Existing directories may be reused as parents, but their modes must not
    change. Identical file content is still a collision: ownership transition
    requires an explicit reviewed policy rather than implicit acceptance.
    This preflight does NOT merge files and grants no install permission.
    """
    installed = Path(installed).absolute()
    staged = Path(staged).absolute()
    if installed == staged or installed in staged.parents or staged in installed.parents:
        raise OwnershipError("installed and staged roots must be separate")
    current = snapshot_imported_root(installed)
    additions = snapshot_imported_root(staged)
    if not additions:
        raise OwnershipError("staged installation contains no entries")
    for name, identity in sorted(additions.items()):
        prior = current.get(name)
        if prior is not None:
            if prior[0] == identity[0] == "dir" and prior[1] == identity[1]:
                continue
            raise OwnershipError(f"staged installation collides with existing entry: {name}")
        parts = Path(name).parts
        for size in range(1, len(parts)):
            parent = Path(*parts[:size]).as_posix()
            existing_parent = current.get(parent) or additions.get(parent)
            if existing_parent is not None and existing_parent[0] != "dir":
                raise OwnershipError(f"staged path has non-directory parent: {name}")
    return additions
