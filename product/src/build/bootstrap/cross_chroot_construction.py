"""Bounded FS-002 diagnostic: collision-safe staged installs through native GCC.

Native GCC is installed only to separate staging; ownership transitions,
functional verification, and artifact publication remain gated.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
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


def omit_native_gcc_staging_lib64_link(stage: Path) -> None:
    """Verify GCC installed through the merged-/usr alias, then drop its duplicate.

    Stage /usr/lib64 is not part of the payload to merge: the imported root
    already owns that exact link. Never delete a real directory or other link.
    Installed runtime files remain in the real stage /usr/lib directory.
    """
    canonical = stage / "usr/lib"
    alias = stage / "usr/lib64"
    try:
        canonical_mode = canonical.lstat().st_mode
        alias_mode = alias.lstat().st_mode
    except FileNotFoundError as exc:
        raise SelectionError("native GCC staging merged-/usr layout is incomplete") from exc
    if not stat.S_ISDIR(canonical_mode) or stat.S_ISLNK(canonical_mode):
        raise SelectionError("native GCC staging usr/lib must be a real directory")
    if not stat.S_ISLNK(alias_mode) or os.readlink(alias) != "lib":
        raise SelectionError("native GCC staging usr/lib64 must be a link to lib")
    alias.unlink()


def verify_native_binutils_structure(root: Path) -> None:
    """Check native Binutils executables without running target binaries.

    ELF structure is only an initial sanity gate, not functional verification.
    """
    for name in ("as", "ld", "ar", "nm", "objdump", "readelf"):
        path = root / "usr/bin" / name
        try:
            meta = path.lstat()
        except FileNotFoundError as exc:
            raise SelectionError(f"missing native Binutils executable: {path}") from exc
        if not stat.S_ISREG(meta.st_mode) or not meta.st_mode & 0o111:
            raise SelectionError(f"native Binutils executable must be a regular executable file: {path}")
        with path.open("rb") as executable:
            header = executable.read(64)
        # ELF64, little-endian, x86-64; executable or position-independent executable.
        if (len(header) < 64 or header[:4] != b"\x7fELF" or
                header[4] != 2 or header[5] != 1 or
                int.from_bytes(header[16:18], "little") not in (2, 3) or
                int.from_bytes(header[18:20], "little") != 62):
            raise SelectionError(f"invalid native x86-64 ELF executable: {path}")


def run_selected_recipes(workspace: Path, manifests: dict, steps: tuple,
                         imported_baseline: dict) -> None:
    """Install ordinary packages and native Binutils without file replacement.

    Run native GCC into an isolated staging root, inventory collisions and
    stop before merging GCC or publishing a cross-chroot artifact.
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
                if collisions:
                    raise RuntimeError(
                        "native Binutils collisions require ownership review; "
                        "native files were not merged"
                    )
                print(f"{prefix}: checking staged native ELF executables", flush=True)
                verify_native_binutils_structure(stage)
                print(f"{prefix}: preflighting noncolliding native installation", flush=True)
                check_staged_install(installed, stage)
                require_preserved_imports(installed, imported_baseline)
                print(f"{prefix}: merging native Binutils without replacements", flush=True)
                merge_staged_install(installed, stage)
                require_preserved_imports(installed, imported_baseline)
                print(f"{prefix}: checking installed native ELF executables", flush=True)
                verify_native_binutils_structure(installed)
                print(f"{prefix}: native Binutils installed; functional verification pending", flush=True)
                print(f"{prefix}: continuing to staged native GCC diagnostic", flush=True)
                shutil.rmtree(stage)
                print(f"{prefix}: installed ({time.monotonic() - started:.1f}s)", flush=True)
                continue
            if step.id == "native-gcc":
                print(f"{prefix}: verifying merged-/usr staging alias", flush=True)
                omit_native_gcc_staging_lib64_link(stage)
                print(f"{prefix}: collecting native GCC collision evidence", flush=True)
                require_preserved_imports(installed, imported_baseline)
                verify_native_binutils_structure(installed)
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
                report = staging_root / "native-gcc-collisions.json"
                with report.open("x", encoding="utf-8") as output:
                    json.dump(evidence, output, sort_keys=True, indent=2)
                    output.write("\n")
                print(f"{prefix}: {len(collisions)} collisions recorded in {report}", flush=True)
                print(f"{prefix}: GCC stage retained for separate ownership review", flush=True)
                raise RuntimeError(
                    "diagnostic stop after native GCC staging: "
                    "GCC merge, native verification and publication remain disabled"
                )
            if step.id.startswith("native-"):
                raise SelectionError("unsupported native construction step")
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
