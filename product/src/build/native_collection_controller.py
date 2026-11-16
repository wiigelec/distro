"""FS-004 native collection controller: independent package production only.

Bootstrap handoff and source provenance are authenticated before any recipe.
This module DOES NOT build or advertise a completed Stage 1C collection.
A package-derived native root is required for construction that needs newly
selected libraries; Stage 1B alone may never masquerade as that provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import subprocess
from typing import Callable

from build.bootstrap.cross_toolchain import _host_jobs
from build.bootstrap.distro_buildroot_import import restore_cross_chroot
from build.bootstrap.cross_chroot_ownership import snapshot_imported_root, require_preserved_imports
from build.native_imported_capabilities import plan_native_packages_from_handoff
from build.native_manifest import load_native_manifests
from build.native_package_execution import NativePackageStep, prepare_native_package, execute_native_package
from build.selection import SelectionError
from build.native_managed_provider import (
    authenticate_managed_candidate, authenticate_managed_prerequisites,
    authenticate_managed_toolchain_seed,
)


@dataclass(frozen=True)
class CollectionPlan:
    archive_sha256: str
    steps: tuple[NativePackageStep, ...]
    bootstrap_root: Path


def _real_empty(path: Path) -> Path:
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_dir() or path.resolve(strict=True) != path or any(path.iterdir()):
        raise SelectionError('FS-004 requires a fresh, real, empty workspace')
    return path


def prepare_collection(workspace: Path, archive: Path, repository: Path, revision: str) -> CollectionPlan:
    """Restore verified Stage 1B and resolve all selected package relationships.

    Source/recipe authority is checked against the immutable Git revision.
    The caller must not treat this bootstrap root as an installed collection.
    """
    workspace = _real_empty(workspace)
    provider = workspace / 'bootstrap-root'
    provider.mkdir()
    restore_cross_chroot(archive, provider)
    evidence, steps = plan_native_packages_from_handoff(repository, revision,
                                                        archive=archive, restored_root=provider)
    if len(steps) != 13 or len({s.name for s in steps}) != 13:
        raise SelectionError('incomplete native payload selection')
    return CollectionPlan(evidence.archive_sha256, steps, provider)


def _selection(step: NativePackageStep, *, revision: int = 1) -> dict:
    """Build-to-Manage schema; only manifest-approved installed relationships."""
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise SelectionError('invalid native package revision')
    if not step.name or not step.version:
        raise SelectionError('incomplete native package identity')
    names = [name for name, _ in step.relationships]
    if names != sorted(set(names)) or step.name in names:
        raise SelectionError('invalid native installed relationships')
    return {'schema_version': 1,
            'identity': {'name': step.name, 'version': step.version,
                         'architecture': 'x86_64', 'revision': revision},
            'relationships': [{'name': name, 'version': ver} for name, ver in step.relationships]}


def _write_selection(exchange: Path, step: NativePackageStep) -> None:
    data = json.dumps(_selection(step), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True) + '\n'
    (exchange / 'selection.json').write_bytes(data.encode('ascii'))


def _manage_create_publish(step: NativePackageStep, exchange: Path,
                           repository: Path, manage: Path) -> None:
    """Call public Manage operations; Build never creates archives or index entries."""
    for args in (
        ('create', '--package', step.name, '--build', str(exchange)),
        ('publish', '--package', step.name, '--repo', str(repository), '--build', str(exchange)),
        ('verify-repo', '--repo', str(repository)),
    ):
        subprocess.run([os.sys.executable, str(manage), *args], check=True,
                       env={'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1'})


def produce_one_native_package(step: NativePackageStep, *, workspace: Path,
                               repository_root: Path, selected_provider: Path,
                               source_repository: Path, manage: Path,
                               jobs: int, linux_headers: Path | None = None,
                               native_seed: Path | None = None) -> Path:
    """Produce one independent package; no staging merges or filesystem copies.

    This API is the per-step unit for the future Manage-driven collection runner.
    The caller must prove `selected_provider` is correct for this step; the
    complete collection controller will only use an authenticated provider.
    """
    workspace = Path(workspace).absolute()
    if workspace.is_symlink() or not workspace.is_dir() or workspace.resolve() != workspace:
        raise SelectionError('invalid native construction workspace')
    if not Path(selected_provider).is_dir() or Path(selected_provider).is_symlink():
        raise SelectionError('missing native construction provider')
    if not Path(manage).is_file() or Path(manage).is_symlink():
        raise SelectionError('Manage CLI is unavailable')
    build = workspace / 'build'
    cache = build / 'sources'
    exchange = workspace / 'exchange' / step.name
    for folder in (build, cache, build / 'steps', exchange, exchange / 'payload'):
        folder.mkdir(parents=True, exist_ok=True)
    if any((exchange / 'payload').iterdir()) or (exchange / 'selection.json').exists():
        raise SelectionError('refusing to reuse native package exchange')
    source, construction = prepare_native_package(step, build, cache, source_repository)
    execute_native_package(step, build, selected_provider, exchange / 'payload',
                           jobs=jobs, source=source, construction=construction,
                           linux_headers=linux_headers, native_seed=native_seed)
    _write_selection(exchange, step)
    _manage_create_publish(step, exchange, repository_root, manage)
    return exchange


def require_collection_provider(plan: CollectionPlan) -> None:
    """Fail closed until Manage provides an independently verified root.

    Stage 1B has bootstrap tools, but not installed Stage 1C Glibc/GCC closure.
    There is deliberately no Stage 1B-only thirteen-package execution loop.
    """
    manifests = load_native_manifests()
    installed_links = {s.name: manifests[s.name].build_link_dependencies
                       for s in plan.steps}
    if any(installed_links.values()):
        raise SelectionError('Stage 1C requires verified Manage-installed construction dependencies; '
                             'Stage 1B is insufficient for complete collection execution')
    raise SelectionError('Manage-installed collection provider is not implemented')


def produce_from_managed_candidate(step: NativePackageStep, *, workspace: Path,
                                   repository_root: Path, installed_root: Path,
                                   source_repository: Path, manage: Path,
                                   jobs: int) -> Path:
    """Build one selected native package through the ordinary shared executor.

    The root is authenticated against Manage repository and installed state,
    then re-authenticated before returning. This remains a candidate-mode
    construction operation, not Stage 1C completion or promotion.
    """
    before = authenticate_managed_candidate(installed_root, repository_root)
    if not any(name == step.name and version == step.version and arch == 'x86_64'
               for name, version, arch, _revision in before.identities):
        raise SelectionError('native package version is outside managed candidate selection')
    result = produce_one_native_package(
        step, workspace=workspace, repository_root=repository_root,
        selected_provider=before.root, source_repository=source_repository,
        manage=manage, jobs=jobs)
    after = authenticate_managed_candidate(installed_root, repository_root)
    if before.identities != after.identities or before.root != after.root:
        raise SelectionError('managed construction provider changed during build')
    return result

def produce_glibc_with_prerequisites(step: NativePackageStep, *, workspace: Path,
                                     repository_root: Path, installed_root: Path,
                                     bootstrap_root: Path, source_repository: Path,
                                     manage: Path, jobs: int) -> Path:
    """Use Stage 1B tools with read-only Manage-installed Linux headers.

    Only Glibc is authorized for this bootstrap transition. Every
    package still executes its own reviewed Bash recipe.
    """
    if step.name != 'glibc' or step.version != '2.44':
        raise SelectionError('prerequisite transition permits only selected Glibc')
    provider = authenticate_managed_prerequisites(installed_root, repository_root)
    if {entry[0] for entry in provider.identities} != {'filesystem', 'linux'}:
        raise SelectionError('unexpected installed construction prerequisites')
    headers = provider.root / 'usr/include'
    result = produce_one_native_package(
        step, workspace=workspace, repository_root=repository_root,
        selected_provider=bootstrap_root, source_repository=source_repository,
        manage=manage, jobs=jobs, linux_headers=headers)
    verified = authenticate_managed_prerequisites(installed_root, repository_root)
    if verified.identities != provider.identities or verified.root != provider.root:
        raise SelectionError('managed Linux headers provider changed during Glibc construction')
    return result


def produce_binutils_with_seed(step: NativePackageStep, *, workspace: Path,
                               repository_root: Path, installed_root: Path,
                               bootstrap_root: Path, source_repository: Path,
                               manage: Path, jobs: int) -> Path:
    """Bootstrap Binutils with Stage 1B tools and a verified read-only native seed.

    The three-package seed is not installed as the runtime root. Build must
    never merge or install package contents itself.
    """
    if step.name != "binutils":
        raise SelectionError("native-seed transition permits only Binutils")
    before = authenticate_managed_toolchain_seed(installed_root, repository_root)
    result = produce_one_native_package(
        step, workspace=workspace, repository_root=repository_root,
        selected_provider=bootstrap_root, source_repository=source_repository,
        manage=manage, jobs=jobs, native_seed=before.root)
    after = authenticate_managed_toolchain_seed(installed_root, repository_root)
    if before.identities != after.identities or before.root != after.root:
        raise SelectionError("managed native seed changed during Binutils construction")
    return result
