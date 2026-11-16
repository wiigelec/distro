"""FS-004 executable bootstrap prefix for selected native package construction.

This deliberately builds only the source-independent filesystem and native Linux
headers using authenticated Stage 1B construction tools. Glibc and subsequent
packages require a separate Manage-derived prerequisite provider; they are NOT
silently constructed against the Stage 1B root. Publishing these two artifacts
never publishes or accepts a completed distro-buildroot collection.
"""
from __future__ import annotations

from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import _host_jobs
from build.host_requirements import qualify_host
from build.native_collection_controller import prepare_collection, produce_one_native_package
from build.native_manifest import load_native_manifests
from build.selection import SelectionError

BOOTSTRAP_PREFIX = ('filesystem', 'linux')


def run_bootstrap_prefix(workspace: Path, archive: Path, *,
                         source_repository: Path, revision: str) -> Path:
    """Run the permitted first two native builds and publish independent artifacts.

    Workspace must be a fresh empty directory. No user-supplied build ordering or
    additional package names are accepted. Failure does not advertise closure.
    """
    if sys.platform != 'linux':
        raise SelectionError('native bootstrap requires a Linux host')
    qualify_host()
    workspace = Path(workspace).absolute()
    source_repository = Path(source_repository).absolute()
    if (source_repository.is_symlink() or not source_repository.is_dir() or
            source_repository.resolve(strict=True) != source_repository):
        raise SelectionError('source repository must be a real directory')
    if workspace == source_repository or workspace.is_relative_to(source_repository):
        raise SelectionError('native workspace must be separate from selected sources')
    plan = prepare_collection(workspace, archive, source_repository, revision)
    selected = {step.name: step for step in plan.steps}
    if set(BOOTSTRAP_PREFIX) - set(selected):
        raise SelectionError('missing selected bootstrap-prefix package')
    manifests = load_native_manifests()
    # Stage 1B authenticates GCC and Make; the filesystem has no construction
    # prerequisites. Linux headers requires those imported tools, not a newly
    # installed Stage 1C C library. Never use this gate for other packages.
    approved_tools = {'gcc', 'make', 'bash', 'binutils'}
    for name in BOOTSTRAP_PREFIX:
        manifest = manifests[name]
        if manifest.build_link_dependencies:
            raise SelectionError(f'{name}: selected Stage 1C link prerequisite blocks bootstrap')
        if set(manifest.build_tools) - approved_tools:
            raise SelectionError(f'{name}: missing authenticated bootstrap tool capability')
    repository = workspace / 'repository'
    repository.mkdir()
    manage = source_repository / 'product/scripts/manage'
    if manage.is_symlink() or not manage.is_file():
        raise SelectionError('Manage CLI not present in source repository')
    jobs = _host_jobs()
    for name in BOOTSTRAP_PREFIX:
        print(f'[distro-buildroot] BOOTSTRAP-PREFIX: {name} {selected[name].version}', flush=True)
        individual = workspace / 'packages' / name
        individual.mkdir(parents=True)
        produce_one_native_package(
            selected[name], workspace=individual, repository_root=repository,
            selected_provider=plan.bootstrap_root, source_repository=source_repository,
            manage=manage, jobs=jobs)
    print('[distro-buildroot] Bootstrap prefix published (filesystem, linux). '
          'No native Glibc, GCC, or complete collection has been built.', flush=True)
    return repository
