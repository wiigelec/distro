"""FS-004 selected native GCC 16.2.0 construction using Manage linker seed.

The restored Stage 1B root is only a bootstrap executor. The independently
installed four-package closure is mounted read-only as native GCC inputs;
construction remains a Bash recipe, with packaging performed by Manage.
"""
from __future__ import annotations

from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import _host_jobs
from build.host_requirements import qualify_host
from build.native_collection_controller import (
    prepare_collection, produce_gcc_with_native_linker_seed,
)
from build.native_managed_provider import authenticate_managed_native_linker_seed
from build.selection import SelectionError


def run_gcc_transition(workspace: Path, archive: Path, *,
                       source_repository: Path, revision: str,
                       linker_repository: Path, installed_linker: Path) -> Path:
    if sys.platform != 'linux':
        raise SelectionError('native GCC transition requires Linux')
    qualify_host()
    workspace = Path(workspace).absolute()
    roots = tuple(Path(p).absolute() for p in (
        source_repository, linker_repository, installed_linker))
    for root in roots:
        if not root.is_dir() or root.is_symlink() or root.resolve(strict=True) != root:
            raise SelectionError('native GCC inputs must be real directories')
        if workspace == root or workspace.is_relative_to(root) or root.is_relative_to(workspace):
            raise SelectionError('native GCC construction workspace overlaps an input')
    source_repository, linker_repository, installed_linker = roots
    authenticate_managed_native_linker_seed(installed_linker, linker_repository)
    plan = prepare_collection(workspace, archive, source_repository, revision)
    matching = [s for s in plan.steps if s.name == 'gcc' and s.version == '16.2.0']
    if len(matching) != 1:
        raise SelectionError('selected native GCC 16.2.0 step missing')
    manage = source_repository / 'product/scripts/manage'
    if manage.is_symlink() or not manage.is_file():
        raise SelectionError('Manage CLI missing from source repository')
    package_workspace = workspace / 'packages' / 'gcc'
    package_workspace.mkdir(parents=True)
    print('[distro-buildroot] GCC 16.2.0: Stage 1B bootstrap compiler; '
          'authenticated Manage linker seed; selected GMP/MPFR/MPC', flush=True)
    result = produce_gcc_with_native_linker_seed(
        matching[0], workspace=package_workspace,
        repository_root=linker_repository, installed_root=installed_linker,
        bootstrap_root=plan.bootstrap_root, source_repository=source_repository,
        manage=manage, jobs=_host_jobs())
    print('[distro-buildroot] GCC package published; complete Stage 1C '
          'collection remains unaccepted', flush=True)
    return result
