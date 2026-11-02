"""FS-002 Stage 1B: verified import and selection; construction not enabled yet."""
from __future__ import annotations

from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import PACKAGES, TARGET
from build.bootstrap.cross_chroot_import import restore_cross_toolchain
from build.bootstrap.cross_chroot_prerequisites import imported_prerequisites
from build.host_requirements import qualify_host
from build.host_sandbox import probe_bubblewrap
from build.selection import load_manifests, select_steps, SelectionError

STAGE = Path(__file__).resolve().parent / "cross-chroot"


def prepare_stage(root: Path, archive: Path):
    """Establish a validated Stage 1B workspace; never claim a completed artifact.

    Deliberately stop before recipe execution until installed-file ownership,
    target-native verification and relocation publication are implemented.
    """
    if sys.platform != "linux":
        raise RuntimeError("Cross-chroot preparation requires a Linux host")
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir() or root.resolve() != root:
        raise SelectionError("Stage 1B workspace must be an existing real directory")
    if any(root.iterdir()):
        raise SelectionError("Stage 1B workspace must be empty")
    qualify_host()
    probe_bubblewrap()
    installed = root / "root"
    build = root / "build"
    installed.mkdir()
    build.mkdir()
    metadata = restore_cross_toolchain(archive, installed)
    imported = imported_prerequisites(metadata, installed)
    manifests = load_manifests(PACKAGES)
    steps = select_steps(
        STAGE / "lists" / "cross-chroot.yaml", manifests, STAGE,
        imported=imported,
    )
    if not steps or metadata["toolchain"]["target"] != TARGET:
        raise SelectionError("invalid Stage 1B selection or target")
    print(f"[cross-chroot] verified Stage 1A import; selected {len(steps)} steps", flush=True)
    raise RuntimeError(
        "Stage 1B construction is not yet enabled: collision ownership, native "
        "verification and portable publication remain unimplemented"
    )
