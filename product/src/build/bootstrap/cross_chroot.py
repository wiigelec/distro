"""FS-002 cross-chroot: verified import and selection; construction not enabled yet."""
from __future__ import annotations

from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import PACKAGES, TARGET
from build.bootstrap.cross_chroot_import import restore_cross_toolchain
from build.bootstrap.cross_chroot_prerequisites import imported_prerequisites
from build.bootstrap.cross_chroot_ownership import snapshot_imported_root
from build.bootstrap.cross_chroot_construction import run_selected_recipes
from build.host_requirements import qualify_host
from build.host_sandbox import probe_bubblewrap
from build.selection import load_manifests, select_steps, SelectionError

STAGE = Path(__file__).resolve().parent / "cross-chroot"


def prepare_stage(root: Path, archive: Path, *, diagnose_native_binutils: bool = False):
    """Validate import and selection, optionally run a non-publishing diagnostic.

    The regular cross-chroot command is deliberately disabled until native
    ownership, functional verification and relocation publication exist.
    Diagnostic mode stages native GCC and records collisions without merging GCC.
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
    if diagnose_native_binutils:
        if len(steps) < 2 or [step.id for step in steps[-2:]] != [
            "native-binutils", "native-gcc"
        ]:
            raise SelectionError("diagnostic requires native Binutils and GCC as the final steps")
        print("[cross-chroot] DIAGNOSTIC ONLY: staging native GCC for collision inventory", flush=True)
        run_selected_recipes(root, manifests, steps, baseline)
        raise RuntimeError("diagnostic runner returned unexpectedly; no verified cross-chroot artifact")
    raise RuntimeError(
        "cross-chroot construction is not yet enabled: collision ownership, native "
        "verification and portable publication remain unimplemented"
    )
