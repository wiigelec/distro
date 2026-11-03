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


def merge_staged_install(installed: Path, staged: Path) -> dict[str, tuple[str, int, str]]:
    """Copy only noncolliding staged entries, with best-effort rollback on failure.

    No replacement or ownership transition is authorized. Call only with
    quiescent, privately controlled roots; concurrent filesystem writers are
    outside this operation's guarantees. Recipe execution remains disabled.
    """
    import shutil

    installed, staged = Path(installed).absolute(), Path(staged).absolute()
    before = snapshot_imported_root(installed)
    planned = check_staged_install(installed, staged)
    if snapshot_imported_root(installed) != before:
        raise OwnershipError("installed filesystem changed during preflight")
    created: list[tuple[Path, str]] = []
    directories: list[tuple[Path, int]] = []
    try:
        # Directories first; never follow installed or staged symlinks.
        for name, identity in sorted(planned.items(), key=lambda item: (item[0].count("/"), item[0])):
            kind, mode, value = identity
            if kind != "dir" or name in before:
                continue
            destination = installed / name
            destination.mkdir(mode=0o700)
            created.append((destination, "dir"))
            directories.append((destination, mode))
        for name, identity in sorted(planned.items()):
            kind, mode, value = identity
            if kind == "dir":
                continue
            destination = installed / name
            origin = staged / name
            if kind == "link":
                os.symlink(value, destination)
                created.append((destination, "link"))
            elif kind == "file":
                read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                source_fd = os.open(origin, read_flags)
                with os.fdopen(source_fd, "rb") as source:
                    output_fd = os.open(destination, write_flags, 0o600)
                    created.append((destination, "file"))
                    with os.fdopen(output_fd, "wb") as output:
                        shutil.copyfileobj(source, output)
                        output.flush()
                        os.fchmod(output.fileno(), mode)
            else:
                raise OwnershipError(f"unsupported staged entry: {name}")
        # A staged payload must not mutate while it is being copied.
        if snapshot_imported_root(staged) != planned:
            raise OwnershipError("staged installation changed during merge")
        # Apply final directory modes only after writing children.
        for directory, mode in sorted(directories, key=lambda entry: -len(entry[0].parts)):
            os.chmod(directory, mode)
        after = snapshot_imported_root(installed)
        for name, identity in before.items():
            if after.get(name) != identity:
                raise OwnershipError(f"existing filesystem entry changed during merge: {name}")
        for name, identity in planned.items():
            if after.get(name) != identity:
                raise OwnershipError(f"merged filesystem entry differs from staging: {name}")
        return planned
    except Exception as exc:
        # Restore write access to newly created parents before rollback.
        for directory, _ in directories:
            try:
                os.chmod(directory, 0o700)
            except OSError:
                pass
        # Roll back this operation's newly created paths, deepest first.
        for path, kind in reversed(created):
            try:
                if kind == "dir":
                    path.rmdir()
                else:
                    path.unlink()
            except OSError:
                pass
        raise OwnershipError(f"staged installation merge failed (inspect target root): {exc}") from exc
