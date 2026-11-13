"""FS-003 first-package native construction diagnostic.

The common native executor is production-shaped, but this bounded diagnostic
must not claim a completed distro-buildroot or publish a Manage package.
"""
from __future__ import annotations

from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import PACKAGES, TARGET, _host_jobs, prepare_step
from build.bootstrap.cross_chroot_ownership import snapshot_imported_root
from build.bootstrap.distro_buildroot_import import restore_cross_chroot
from build.host_requirements import qualify_host
from build.native_sandbox import run_native_recipe
from build.selection import SelectionError, load_manifests, select_steps

STAGE = Path(__file__).resolve().parent / "distro-buildroot"


def run_diagnostic(root: Path, archive: Path) -> None:
    """Build and stage one Sed package; deliberately fail before publication.

    Full Stage 1C success awaits standard Manage create/publish, verification,
    and requirement reactivation. The diagnostic preserves its staged output.
    """
    if sys.platform != "linux":
        raise SelectionError("native buildroot requires a Linux host")
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
        raise SelectionError("native buildroot workspace must be a real directory")
    if any(root.iterdir()):
        raise SelectionError("native buildroot workspace must be empty")
    qualify_host()
    manifests = load_manifests(PACKAGES)
    steps = select_steps(STAGE / "lists/distro-buildroot.yaml", manifests, STAGE)
    if len(steps) != 1 or (steps[0].name, steps[0].version) != ("sed", "4.10"):
        raise SelectionError("FS-003 diagnostic requires exactly the pinned Sed package")
    build, imported, staged = root / "build", root / "root", root / "staging"
    for path in (build, imported, staged):
        path.mkdir()
    restore_cross_chroot(archive, imported)
    # Source access and verification happen in Build's controller on the host;
    # recipe execution itself is entirely target-native in the isolated root.
    cache = build / "sources"
    cache.mkdir()
    (build / "steps").mkdir()
    step = steps[0]
    source, construction = prepare_step(step, manifests[step.name], build, cache)
    package_stage = staged / step.id
    package_stage.mkdir()
    jobs = _host_jobs()
    print("[distro-buildroot] DIAGNOSTIC: native Sed construction", flush=True)
    run_native_recipe(
        build, imported, package_stage, step.recipe,
        source_dir="/work/" + source.relative_to(build).as_posix(),
        build_dir="/work/" + construction.relative_to(build).as_posix(),
        package=step.name, version=step.version, step_id=step.id,
        target=TARGET, jobs=jobs,
    )
    stage_inventory = snapshot_imported_root(package_stage)
    if not any(path.startswith("usr/bin/sed") and kind[0] == "file"
               for path, kind in stage_inventory.items()):
        raise SelectionError("native Sed did not install an independent usr/bin/sed")
    print(f"[distro-buildroot] Native staging contains {len(stage_inventory)} entries", flush=True)
    raise RuntimeError(
        "FS-003 diagnostic reached native Sed staging; Manage creation, "
        "publication and independent verification not yet implemented"
    )
