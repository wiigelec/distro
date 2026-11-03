"""Bounded cross-chroot package construction with staged, collision-checked installs.

This runner is not yet called from the public CLI: native tool ownership
transitions, functional verification and artifact publication remain gated.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import time

from build.bootstrap.cross_toolchain import TARGET, _host_jobs, prepare_step
from build.bootstrap.cross_chroot_ownership import (
    check_staged_install, merge_staged_install, require_preserved_imports,
    snapshot_imported_root,
)
from build.bootstrap.cross_chroot_sandbox import run_staged_recipe
from build.selection import SelectionError


def run_selected_recipes(workspace: Path, manifests: dict, steps: tuple,
                         imported_baseline: dict) -> None:
    """Build only ordinary selected packages, rejecting all file replacements.

    The caller must first validate/restore the cross-toolchain and select
    dependencies. A failed construction leaves the workspace unpublished.
    No native-binutils/native-gcc transition is authorized by this runner.
    """
    workspace = Path(workspace).absolute()
    if workspace.is_symlink() or not workspace.is_dir() or workspace.resolve() != workspace:
        raise SelectionError("cross-chroot workspace must be a real directory")
    build, installed = workspace / "build", workspace / "root"
    if not build.is_dir() or build.is_symlink() or not installed.is_dir() or installed.is_symlink():
        raise SelectionError("cross-chroot build and installed roots are required")
    if not steps:
        raise SelectionError("empty cross-chroot selection")
    require_preserved_imports(installed, imported_baseline)
    if any(step.id.startswith("native-") for step in steps):
        raise SelectionError(
            "native Binutils/GCC ownership transitions are not yet authorized"
        )
    staging_root = workspace / "staging"
    if staging_root.exists() or staging_root.is_symlink():
        raise SelectionError("cross-chroot staging root already exists")
    staging_root.mkdir()
    cache = build / "sources"
    cache.mkdir(exist_ok=False)
    (build / "steps").mkdir(exist_ok=False)
    jobs = _host_jobs()
    print(f"[cross-chroot] Recipe runner ready: {len(steps)} steps, make -j{jobs}", flush=True)
    for index, step in enumerate(steps, 1):
        started = time.monotonic()
        prefix = f"[cross-chroot] [{index}/{len(steps)}] {step.id} ({step.version})"
        if step.name not in manifests:
            raise SelectionError(f"missing authoritative manifest: {step.name}")
        stage = staging_root / step.id
        if stage.exists() or stage.is_symlink():
            raise SelectionError(f"staging directory already exists: {step.id}")
        stage.mkdir()
        print(f"{prefix}: fetching and verifying sources", flush=True)
        try:
            source, construction = prepare_step(step, manifests[step.name], build, cache)
            print(f"{prefix}: executing isolated recipe", flush=True)
            run_staged_recipe(
                build, installed, stage, step.recipe,
                source_dir="/work/" + source.relative_to(build).as_posix(),
                build_dir="/work/" + construction.relative_to(build).as_posix(),
                package=step.name, version=step.version, step_id=step.id,
                target=TARGET, jobs=jobs,
            )
            print(f"{prefix}: checking staged installation ownership", flush=True)
            check_staged_install(installed, stage)
            require_preserved_imports(installed, imported_baseline)
            print(f"{prefix}: merging noncolliding files", flush=True)
            merge_staged_install(installed, stage)
            require_preserved_imports(installed, imported_baseline)
        except Exception as exc:
            print(f"{prefix}: FAILED ({exc}); retaining staging for inspection", flush=True)
            raise RuntimeError(f"cross-chroot {step.id} failed: {exc}") from exc
        shutil.rmtree(stage)
        print(f"{prefix}: installed ({time.monotonic() - started:.1f}s)", flush=True)
    # Completion of package installation does not constitute a functional gate.
    print("[cross-chroot] Package installation complete; native verification pending", flush=True)
