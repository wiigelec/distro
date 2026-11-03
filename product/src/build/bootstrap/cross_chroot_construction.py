"""Bounded cross-chroot package construction with staged, collision-checked installs.

This runner is not yet called from the public CLI: native tool ownership
transitions, functional verification and artifact publication remain gated.
"""
from __future__ import annotations

from pathlib import Path
import json
import shutil
import stat
import time

from build.bootstrap.cross_toolchain import TARGET, _host_jobs, prepare_step
from build.bootstrap.cross_chroot_ownership import (
    check_staged_install, merge_staged_install, require_preserved_imports,
)
from build.bootstrap.cross_chroot_sandbox import run_staged_recipe
from build.bootstrap.cross_chroot_transitions import native_collision_evidence
from build.selection import SelectionError


def omit_generated_info_index(stage: Path) -> None:
    """Exclude only GNU Info's shared, generated menu index from staged DESTDIR.

    Individual .info manuals remain staged. Rebuilding the combined target
    index is a later governed operation, not an ownership collision exception.
    """
    index = stage / "usr/share/info/dir"
    try:
        mode = index.lstat().st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISREG(mode):
        raise SelectionError(f"unexpected staged GNU Info index type: {index}")
    index.unlink()


def run_selected_recipes(workspace: Path, manifests: dict, steps: tuple,
                         imported_baseline: dict) -> None:
    """Install ordinary packages; capture native Binutils evidence then stop.

    The caller must first validate/restore the cross-toolchain and select
    dependencies. No native ownership transition is permitted. This path
    never completes a full cross-chroot artifact or enters native GCC.
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
    native_ids = [step.id for step in steps if step.id.startswith("native-")]
    if native_ids and native_ids != ["native-binutils", "native-gcc"]:
        raise SelectionError("native package steps must end with native-binutils then native-gcc")
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
            # Exclude the shared generated Info menu before either ordinary
            # ownership preflight or native Binutils collision inventory.
            omit_generated_info_index(stage)
            if step.id == "native-binutils":
                print(f"{prefix}: collecting native collision evidence", flush=True)
                require_preserved_imports(installed, imported_baseline)
                collisions = native_collision_evidence(installed, stage)
                evidence = {
                    "schema_version": 1,
                    "step_id": step.id,
                    "target": TARGET,
                    "version": step.version,
                    "collisions": {
                        name: {"installed": list(prior), "staged": list(candidate)}
                        for name, (prior, candidate) in sorted(collisions.items())
                    },
                }
                report = staging_root / "native-binutils-collisions.json"
                # Exclusive creation prevents replacing previously reviewed evidence.
                with report.open("x", encoding="utf-8") as output:
                    json.dump(evidence, output, sort_keys=True, indent=2)
                    output.write("\n")
                print(
                    f"{prefix}: {len(collisions)} collisions recorded in {report}; "
                    "staged files retained",
                    flush=True,
                )
                raise RuntimeError(
                    "native Binutils installation requires explicit ownership review; "
                    "no native files merged and no artifact published"
                )
            if step.id.startswith("native-"):
                raise SelectionError("native GCC construction remains disabled")
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
