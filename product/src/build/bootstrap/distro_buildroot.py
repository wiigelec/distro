"""FS-003 initial native package: shared Build runner and Manage handoff.

Only the selected Sed 4.10 package is produced. This is not an assertion that
the distro-buildroot collection or the Functional Set is accepted.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys

from build.bootstrap.cross_toolchain import PACKAGES, TARGET, _host_jobs, prepare_step
from build.bootstrap.cross_chroot_ownership import snapshot_imported_root, require_preserved_imports
from build.bootstrap.distro_buildroot_import import restore_cross_chroot
from build.host_requirements import qualify_host
from build.native_sandbox import run_native_recipe, verify_staged_sed
from build.selection import SelectionError, load_manifests, select_steps

STAGE = Path(__file__).resolve().parent / "distro-buildroot"


def run_stage(root: Path, archive: Path, *, diagnostic: bool = False) -> Path | None:
    """Construct one target-native Sed package with the shared Build execution.

    Diagnostic mode retains the legacy staged output and exits unsuccessfully.
    Normal mode delegates archive and index operations to Manage.
    """
    if sys.platform != "linux":
        raise SelectionError("native buildroot requires a Linux host")
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
        raise SelectionError("native buildroot workspace must be a real directory")
    if any(root.iterdir()):
        raise SelectionError("native buildroot workspace must be empty")
    print("[distro-buildroot] Qualifying host tools", flush=True)
    qualify_host()
    print("[distro-buildroot] Selecting native packages", flush=True)
    manifests = load_manifests(PACKAGES)
    steps = select_steps(STAGE / "lists/distro-buildroot.yaml", manifests, STAGE)
    if len(steps) != 1 or (steps[0].name, steps[0].version) != ("sed", "4.10"):
        raise SelectionError("FS-003 diagnostic requires exactly the pinned Sed package")
    build, imported, staged = root / "build", root / "root", root / "staging"
    for path in (build, imported, staged):
        path.mkdir()
    print("[distro-buildroot] Verifying and restoring Stage 1B handoff", flush=True)
    restore_cross_chroot(archive, imported)
    print("[distro-buildroot] Stage 1B handoff restored", flush=True)
    # Source access and verification happen in Build's controller on the host;
    # recipe execution itself is entirely target-native in the isolated root.
    cache = build / "sources"
    cache.mkdir()
    (build / "steps").mkdir()
    step = steps[0]
    print(f"[distro-buildroot] Fetching and verifying {step.name} {step.version} sources", flush=True)
    source, construction = prepare_step(step, manifests[step.name], build, cache)
    print(f"[distro-buildroot] Verified sources ready", flush=True)
    # Build creates the fixed identity and manifest-selected relationships.
    # The initial Sed manifest has no dependencies; future resolved selections
    # must not be silently guessed from Bootstrap input or ELF observation.
    if manifests[step.name].dependencies:
        raise SelectionError("unresolved install relationships are not permitted")
    baseline = snapshot_imported_root(imported)
    if diagnostic:
        package_stage = staged / step.id
        package_stage.mkdir()
        exchange = None
    else:
        exchange = root / "exchange" / step.id
        exchange.mkdir(parents=True)
        package_stage = exchange / "payload"
        package_stage.mkdir()
    jobs = _host_jobs()
    label = "DIAGNOSTIC" if diagnostic else "BUILD"
    print(f"[distro-buildroot] {label}: starting native {step.name} {step.version} recipe (make -j{jobs})", flush=True)
    run_native_recipe(
        build, imported, package_stage, step.recipe,
        source_dir="/work/" + source.relative_to(build).as_posix(),
        build_dir="/work/" + construction.relative_to(build).as_posix(),
        package=step.name, version=step.version, step_id=step.id,
        target=TARGET, jobs=jobs,
    )
    print("[distro-buildroot] Native recipe returned; inventorying staged output", flush=True)
    stage_inventory = snapshot_imported_root(package_stage)
    if not any(path.startswith("usr/bin/sed") and kind[0] == "file"
               for path, kind in stage_inventory.items()):
        raise SelectionError("native Sed did not install an independent usr/bin/sed")
    print(f"[distro-buildroot] Native staging contains {len(stage_inventory)} entries", flush=True)
    require_preserved_imports(imported, baseline)
    print("[distro-buildroot] Verifying staged Sed inside the target-native runtime", flush=True)
    verify_staged_sed(imported, package_stage)
    print("[distro-buildroot] Native staged Sed functional verification passed", flush=True)
    if diagnostic:
        raise RuntimeError("FS-003 diagnostic reached native Sed staging; "
                           "no package created or published")

    assert exchange is not None
    selection = {
        "schema_version": 1,
        "identity": {"name": step.name, "version": step.version,
                     "architecture": "x86_64", "revision": 1},
        "relationships": [],
    }
    selection_bytes = (json.dumps(selection, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=True) + "\n").encode("ascii")
    with (exchange / "selection.json").open("xb") as selected:
        selected.write(selection_bytes)
    manage = Path(__file__).resolve().parents[3] / "scripts" / "manage"
    # Manage is invoked through its public operations, not imported into Build.
    # In particular Build never serializes a package or modifies the index.
    commands = (
        ("create", "--package", step.name, "--build", str(exchange)),
        ("publish", "--package", step.name, "--repo", str(root / "repository"),
         "--build", str(exchange)),
        ("verify-repo", "--repo", str(root / "repository")),
    )
    repository = root / "repository"
    repository.mkdir()
    for command in commands:
        print(f"[distro-buildroot] Manage {command[0]}", flush=True)
        subprocess.run([sys.executable, str(manage), *command], check=True,
                       env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"})
    require_preserved_imports(imported, baseline)
    print("[distro-buildroot] One native Sed package published and repository verified; "
          "distro-buildroot collection remains incomplete", flush=True)
    return repository / "artifacts" / "sed-4.10-x86_64-r1.tar.xz"


def run_diagnostic(root: Path, archive: Path) -> None:
    run_stage(root, archive, diagnostic=True)
