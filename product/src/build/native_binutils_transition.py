"""FS-004 bounded native Binutils bootstrap using Manage-installed Glibc seed.

The selected three-package root is exposed read-only as a prerequisite,
not promoted to an accepted or runnable native buildroot.
"""
from __future__ import annotations

from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import _host_jobs
from build.host_requirements import qualify_host
from build.native_collection_controller import (
    prepare_collection, produce_binutils_with_seed,
)
from build.native_managed_provider import authenticate_managed_toolchain_seed
from build.selection import SelectionError


def run_binutils_transition(workspace: Path, archive: Path, *,
                            source_repository: Path, revision: str,
                            seed_repository: Path, installed_seed: Path) -> Path:
    if sys.platform != "linux":
        raise SelectionError("native Binutils requires Linux")
    qualify_host()
    workspace = Path(workspace).absolute()
    inputs = tuple(Path(p).absolute() for p in (
        source_repository, seed_repository, installed_seed))
    for path in inputs:
        if not path.is_dir() or path.is_symlink() or path.resolve(strict=True) != path:
            raise SelectionError("native Binutils requires real input directories")
        if (workspace == path or workspace.is_relative_to(path)
                or path.is_relative_to(workspace)):
            raise SelectionError("Binutils workspace must not overlap any input")
    source_repository, seed_repository, installed_seed = inputs
    authenticate_managed_toolchain_seed(installed_seed, seed_repository)
    plan = prepare_collection(workspace, archive, source_repository, revision)
    selected = [step for step in plan.steps if step.name == "binutils"]
    if len(selected) != 1:
        raise SelectionError("selected native Binutils recipe is missing")
    manage = source_repository / "product/scripts/manage"
    if manage.is_symlink() or not manage.is_file():
        raise SelectionError("Manage CLI unavailable")
    package_workspace = workspace / "packages" / "binutils"
    package_workspace.mkdir(parents=True)
    print("[distro-buildroot] BINUTILS: using managed Glibc seed and Stage 1B tools",
          flush=True)
    result = produce_binutils_with_seed(
        selected[0], workspace=package_workspace,
        repository_root=seed_repository, installed_root=installed_seed,
        bootstrap_root=plan.bootstrap_root, source_repository=source_repository,
        manage=manage, jobs=_host_jobs())
    print("[distro-buildroot] Binutils package published; Stage 1C remains incomplete",
          flush=True)
    return result
