"""Verified Stage 1A filesystem import for FS-002 (not a stage runner)."""
from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess

from build.bootstrap.cross_toolchain import TARGET, _validate_candidate_archive
from build.bootstrap.cross_toolchain_metadata import ARCHIVE_NAME, METADATA_NAME, validate_handoff


class CrossChrootImportError(RuntimeError):
    """Input handoff is invalid or cannot be restored safely."""


def restore_cross_toolchain(archive: Path, installed: Path) -> dict:
    """Validate a complete Stage 1A handoff, then restore into a fresh directory.

    The directory must already exist, be empty, and have no symlinked parents.
    Does not run any recipe, change host paths, or claim Stage 1B completion.
    """
    archive, installed = Path(archive).absolute(), Path(installed).absolute()
    if archive.name != ARCHIVE_NAME or archive.is_symlink() or not archive.is_file():
        raise CrossChrootImportError("expected a regular cross-toolchain.tar.xz")
    metadata_path = archive.parent / METADATA_NAME
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise CrossChrootImportError("matching cross-toolchain.json is required")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        validate_handoff(archive, metadata)
        if metadata["toolchain"]["target"] != TARGET:
            raise ValueError("Stage 1A target does not match Stage 1B")
        _validate_candidate_archive(archive)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        raise CrossChrootImportError(f"invalid Stage 1A handoff: {exc}") from exc
    if (installed.is_symlink() or not installed.is_dir() or
            installed.resolve(strict=True) != installed or any(installed.iterdir())):
        raise CrossChrootImportError("destination must be an existing, empty real directory")
    # Refuse a link anywhere in the parent chain, including the immediate parent.
    current = installed.parent
    while current != current.parent:
        if current.is_symlink():
            raise CrossChrootImportError("destination parent must not be symlinked")
        current = current.parent
    try:
        subprocess.run(["tar", "-xJf", str(archive), "-C", str(installed),
                        "--no-same-owner", "--no-overwrite-dir"],
                       check=True, env={"PATH": os.defpath})
    except (OSError, subprocess.CalledProcessError) as exc:
        # Callers must discard the destination after any extraction failure.
        raise CrossChrootImportError(f"Stage 1A extraction failed (discard destination): {exc}") from exc
    return metadata
