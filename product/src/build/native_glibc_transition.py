"""FS-004 native Glibc bootstrap transition using Manage-installed headers.

Restored Stage 1B tools remain the authenticated executor. The selected Linux
headers enter the shared sandbox only through a read-only, path-isolated mount.
This does NOT install or promote Glibc into a completed native collection.
"""
from __future__ import annotations

from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import _host_jobs
from build.host_requirements import qualify_host
from build.native_collection_controller import prepare_collection, produce_glibc_with_prerequisites
from build.selection import SelectionError
from build.native_managed_provider import authenticate_managed_prerequisites


def run_glibc_transition(workspace: Path, archive: Path, *, source_repository: Path,
                         revision: str, prerequisite_repository: Path,
                         installed_prerequisites: Path) -> Path:
    if sys.platform != 'linux':
        raise SelectionError('Glibc transition requires a Linux construction host')
    qualify_host()
    workspace = Path(workspace).absolute()
    prerequisite_repository = Path(prerequisite_repository).absolute()
    installed_prerequisites = Path(installed_prerequisites).absolute()
    source_repository = Path(source_repository).absolute()
    for root in (source_repository, prerequisite_repository, installed_prerequisites):
        if (not root.is_dir() or root.is_symlink() or root.resolve(strict=True) != root):
            raise SelectionError('Glibc transition inputs must be real directories')
    roots = (source_repository, prerequisite_repository, installed_prerequisites)
    if any(workspace == p or workspace.is_relative_to(p) or p.is_relative_to(workspace)
           for p in roots):
        raise SelectionError('Glibc construction workspace overlaps an input root')
    authenticate_managed_prerequisites(installed_prerequisites, prerequisite_repository)
    plan = prepare_collection(workspace, archive, source_repository, revision)
    steps = [s for s in plan.steps if s.name == 'glibc' and s.version == '2.44']
    if len(steps) != 1:
        raise SelectionError('selected Glibc 2.44 construction recipe missing')
    manage = source_repository / 'product/scripts/manage'
    if manage.is_symlink() or not manage.is_file():
        raise SelectionError('Manage CLI unavailable in selected source repository')
    package_workspace = workspace / 'packages' / 'glibc'
    package_workspace.mkdir(parents=True)
    print('[distro-buildroot] GLIBC: authenticated headers and Stage 1B tools; '
          'starting target-native Bash recipe', flush=True)
    result = produce_glibc_with_prerequisites(
        steps[0], workspace=package_workspace,
        repository_root=prerequisite_repository,
        installed_root=installed_prerequisites,
        bootstrap_root=plan.bootstrap_root, source_repository=source_repository,
        manage=manage, jobs=_host_jobs())
    print('[distro-buildroot] Glibc artifact published; complete Stage 1C '
          'collection remains unaccepted', flush=True)
    return result
