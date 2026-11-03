"""FS-002 cross-chroot: verified import and selection; construction not enabled yet."""
from __future__ import annotations

from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import PACKAGES, TARGET
from build.bootstrap.cross_chroot_import import restore_cross_toolchain
from build.bootstrap.cross_chroot_prerequisites import imported_prerequisites
from build.bootstrap.cross_chroot_ownership import snapshot_imported_root
from build.host_requirements import qualify_host
from build.host_sandbox import probe_bubblewrap
from build.selection import load_manifests, select_steps, SelectionError

STAGE = Path(__file__).resolve().parent / "cross-chroot"


def prepare_stage(root: Path, archive: Path):
    """Establish a validated cross-chroot workspace; never claim a completed artifact.

    Deliberately stop before recipe execution until installed-file ownership,
    target-native verification and relocation publication are implemented.
    """
    if sys.platform != "linux":
        raise RuntimeError("Cross-chroot preparation requires a Linux host")
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir() or root.resolve() != root:
        raise SelectionError("cross-chroot workspace must be an existing real directory")
    if any(root.iterdir()):
        raise SelectionError("cross-chroot workspace must be empty")
    print("[cross-chroot] Qualifying host tools", flush=True)
    qualify_host()
    print("[cross-chroot] Checking Bubblewrap isolation", flush=True)
    probe_bubblewrap()
    installed = root / "root"
    build = root / "build"
    installed.mkdir()
    build.mkdir()
    print("[cross-chroot] Verifying and restoring cross-toolchain handoff", flush=True)
    metadata = restore_cross_toolchain(archive, installed)
    print("[cross-chroot] Verifying imported prerequisites", flush=True)
    imported = imported_prerequisites(metadata, installed)
    print("[cross-chroot] Resolving cross-chroot package selection", flush=True)
    manifests = load_manifests(PACKAGES)
    steps = select_steps(
        STAGE / "lists" / "cross-chroot.yaml", manifests, STAGE,
        imported=imported,
    )
    if not steps or metadata["toolchain"]["target"] != TARGET:
        raise SelectionError("invalid cross-chroot selection or target")
    print("[cross-chroot] Recording cross-toolchain filesystem ownership", flush=True)
    baseline = snapshot_imported_root(installed)
    print(f"[cross-chroot] Imported {len(baseline)} entries; selected {len(steps)} steps", flush=True)
    raise RuntimeError(
        "cross-chroot construction is not yet enabled: collision ownership, native "
        "verification and portable publication remain unimplemented"
    )
