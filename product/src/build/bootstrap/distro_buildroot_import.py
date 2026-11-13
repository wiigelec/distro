"""FS-003: verified Stage 1B import for the initial native buildroot.

The imported filesystem is temporary construction input, never a collection of
Manage-installed packages. This module never creates or publishes packages.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from build.bootstrap.cross_chroot_handoff import (
    ARCHIVE_NAME, METADATA_NAME, validate_cross_chroot_handoff,
)
from build.selection import SelectionError


class BuildrootImportError(RuntimeError):
    """A Stage 1B input cannot safely establish the native construction root."""


def _real_empty_directory(destination: Path) -> None:
    if (destination.is_symlink() or not destination.is_dir() or
            destination.resolve(strict=True) != destination or any(destination.iterdir())):
        raise BuildrootImportError("destination must be an existing empty real directory")
    current = destination.parent
    while True:
        if current.is_symlink():
            raise BuildrootImportError("destination parent must not be symlinked")
        if current == current.parent:
            break
        current = current.parent


def restore_cross_chroot(archive: Path, destination: Path) -> dict:
    """Restore a complete Stage 1B handoff to a separate, empty destination.

    Verification, including the archive member safety check, precedes extraction.
    A failed extraction is not a valid root and must be discarded by the caller.
    """
    archive = Path(archive).absolute()
    destination = Path(destination).absolute()
    if (archive.name != ARCHIVE_NAME or archive.is_symlink() or
            not archive.is_file()):
        raise BuildrootImportError("expected a regular cross-chroot.tar.xz")
    metadata_path = archive.parent / METADATA_NAME
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise BuildrootImportError("matching cross-chroot.json is required")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        validate_cross_chroot_handoff(archive, metadata)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, SelectionError) as exc:
        raise BuildrootImportError(f"invalid Stage 1B handoff: {exc}") from exc
    _real_empty_directory(destination)
    if archive.is_relative_to(destination):
        raise BuildrootImportError("input archive must be separate from destination")
    try:
        subprocess.run(
            ["tar", "-xJf", str(archive), "-C", str(destination),
             "--no-same-owner", "--no-overwrite-dir"],
            check=True, env={"PATH": os.defpath}, timeout=600,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise BuildrootImportError(
            f"Stage 1B restoration failed; discard candidate root: {exc}"
        ) from exc
    return metadata
