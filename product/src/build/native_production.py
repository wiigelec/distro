"""FS-004 integrated package-production bootstrap, no collection promotion.

All package bytes go through the accepted Build-to-Manage exchange. This
first integrated slice builds the four authoritative prerequisite artifacts
in dependency order; it refuses to represent a partial result as the full
19-package collection. The remaining native execution provider is a separate
Build integration task, not an excuse to run later recipes against Stage 1B.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from build.bootstrap.cross_toolchain import _host_jobs
from build.host_requirements import qualify_host
from build.native_collection_controller import (
    prepare_collection, produce_one_native_package,
    produce_glibc_with_prerequisites, produce_binutils_with_seed,
    produce_gcc_with_native_linker_seed,
)
from build.selection import SelectionError
from build.native_managed_provider import authenticate_managed_native_compiler_seed
from build.host_sandbox import _bwrap
import os
from manage.repository import verify_repository, INDEX, ARTIFACTS, LOCK
from manage.package import PackageError, _regular_directory

EXPECTED = ('filesystem', 'linux', 'glibc', 'binutils', 'gcc')


def _separate(workspace: Path, source: Path, publication: Path, archive: Path) -> None:
    for p in (source, publication, archive):
        if workspace == p or workspace.is_relative_to(p) or p.is_relative_to(workspace):
            raise SelectionError('workspace overlaps an input or publication destination')
    if source == publication or source.is_relative_to(publication) or publication.is_relative_to(source):
        raise SelectionError('publication must be separate from immutable source repository')
    if publication == archive or publication.is_relative_to(archive) or archive.is_relative_to(publication):
        raise SelectionError('publication overlaps Stage 1B handoff')


def _manage(manage: Path, *arguments: str) -> None:
    subprocess.run([sys.executable, str(manage), *arguments],
                   check=True, env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'})


def _smoke_native_compiler_seed(root: Path) -> None:
    """Compile C using only selected GCC, Binutils and Glibc in bwrap.

    Bash and Make remain unavailable here: this is not a native buildroot.
    """
    cmd = [
        _bwrap(), '--die-with-parent', '--unshare-user', '--unshare-pid',
        '--unshare-net', '--new-session', '--clearenv',
        '--ro-bind', str(root), '/', '--dev', '/dev', '--proc', '/proc',
        '--tmpfs', '/tmp', '--tmpfs', '/run',
        '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'LC_ALL', 'C',
        '--', '/usr/bin/gcc', '-x', 'c', '-c', '-', '-o', '/tmp/fs004-probe.o',
    ]
    source = b'int fs004_compiler_probe(void) { return 42; }\n'
    result = subprocess.run(cmd, input=source, capture_output=True,
                            env={'PATH': os.defpath}, timeout=120)
    if result.returncode:
        raise SelectionError('isolated native compiler/assembler smoke failed: '
                             + result.stderr.decode('utf-8', 'replace')[-2000:])
    print('[distro-buildroot] Native compiler/assembler seed smoke passed (isolated)',
          flush=True)


def run_package_production(workspace: Path, archive: Path, publication: Path) -> None:
    """Run authenticated production prefix and fail closed at unsupported handoff.

    Publication holds independently verified ordinary packages, *not* a
    completed-collection selector or an accepted Stage 1C buildroot.
    """
    if sys.platform != 'linux':
        raise SelectionError('FS-004 native package production requires Linux')
    qualify_host()
    workspace = Path(workspace).absolute()
    archive = Path(archive).absolute()
    publication = Path(publication).absolute()
    # Package selection and script provenance are tied to the actual
    # checked-out commit; users do not provide arbitrary source revisions.
    source = Path(__file__).resolve().parents[3]
    if source.is_symlink() or not source.is_dir() or source.resolve(strict=True) != source:
        raise SelectionError('invalid selected source repository')
    if archive.is_symlink() or not archive.is_file():
        raise SelectionError('Stage 1B handoff must be a real archive')
    if publication.is_symlink():
        raise SelectionError('publish destination must not be a symlink')
    if publication.exists():
        try:
            _regular_directory(publication)
        except PackageError as exc:
            raise SelectionError(f'unsafe existing publish repository: {exc}') from exc
    if not publication.parent.is_dir() or publication.parent.is_symlink():
        raise SelectionError('publish parent must be an existing real directory')
    _separate(workspace, source, publication, archive)
    manage = source / 'product/scripts/manage'
    if manage.is_symlink() or not manage.is_file():
        raise SelectionError('Manage CLI unavailable')
    revision = subprocess.check_output(
        ['git', '-C', str(source), 'rev-parse', '--verify', 'HEAD^{commit}'],
        text=True, timeout=30).strip()
    plan = prepare_collection(workspace, archive, source, revision)
    steps = {step.name: step for step in plan.steps}
    if len(steps) != 19 or set(EXPECTED) - set(steps):
        raise SelectionError('incomplete native package selection')
    jobs = _host_jobs()
    if not publication.exists():
        publication.mkdir()
    # Manage's index, not the presence of an artifact filename, is publication
    # authority. Verify the entire repository before selecting any reuse.
    if (publication / LOCK).exists() or (publication / LOCK).is_symlink():
        raise SelectionError('existing Manage publish lock; manual recovery required')
    if (publication / INDEX).exists() or (publication / INDEX).is_symlink():
        try:
            records = verify_repository(publication)['packages']
        except (PackageError, OSError) as exc:
            raise SelectionError(f'existing Manage repository verification failed: {exc}') from exc
    elif any(publication.iterdir()):
        # An orphan archive, unindexed payload or interrupted first publish
        # is never eligible for automatic recovery or filename-based skipping.
        raise SelectionError('nonempty publish destination has no Manage index')
    else:
        records = []
    published = {}
    for record in records:
        ident = record['identity']
        name = ident['name']
        if name not in steps or name in published:
            raise SelectionError(f'unselected or duplicate published native package: {name}')
        expected = {'name': name, 'version': steps[name].version,
                    'architecture': 'x86_64', 'revision': 1}
        relationships = [{'name': n, 'version': v} for n, v in steps[name].relationships]
        if ident != expected or record['relationships'] != relationships:
            raise SelectionError(f'published {name} differs from selected identity/relationships; '
                                 'new packaging revision required')
        published[name] = record
    print(f'[distro-buildroot] Reusing {len(published)} verified published package(s)',
          flush=True)

    def skip(name: str) -> bool:
        if name not in published:
            return False
        # Recheck for external mutation before bypassing the package recipe.
        try:
            verified = verify_repository(publication)['packages']
        except (PackageError, OSError) as exc:
            raise SelectionError(f'published package changed: {exc}') from exc
        if not any(record == published[name] for record in verified):
            raise SelectionError(f'published {name} changed during resume')
        print(f'[distro-buildroot] Skipping {name} {steps[name].version} '
              '(already Manage-verified in --publish)', flush=True)
        return True

    def build(name: str, provider: Path, **kwargs) -> None:
        if skip(name):
            return
        location = workspace / 'packages' / name
        location.mkdir(parents=True)
        print(f'[distro-buildroot] Producing {name} {steps[name].version}', flush=True)
        produce_one_native_package(
            steps[name], workspace=location, repository_root=publication,
            selected_provider=provider, source_repository=source,
            manage=manage, jobs=jobs, **kwargs)

    for name in ('filesystem', 'linux'):
        build(name, plan.bootstrap_root)
    prerequisites = workspace / 'installed-prerequisites'
    _manage(manage, 'install-prerequisites', '--repo', str(publication),
            '--root', str(prerequisites))
    if not skip('glibc'):
        glibc_workspace = workspace / 'packages/glibc'
        glibc_workspace.mkdir(parents=True)
        produce_glibc_with_prerequisites(
            steps['glibc'], workspace=glibc_workspace,
            repository_root=publication, installed_root=prerequisites,
            bootstrap_root=plan.bootstrap_root, source_repository=source,
            manage=manage, jobs=jobs)
    toolchain_seed = workspace / 'installed-toolchain-seed'
    _manage(manage, 'install-toolchain-seed', '--repo', str(publication),
            '--root', str(toolchain_seed))
    if not skip('binutils'):
        binutils_workspace = workspace / 'packages/binutils'
        binutils_workspace.mkdir(parents=True)
        produce_binutils_with_seed(
            steps['binutils'], workspace=binutils_workspace,
            repository_root=publication, installed_root=toolchain_seed,
            bootstrap_root=plan.bootstrap_root, source_repository=source,
            manage=manage, jobs=jobs)
    linker_seed = workspace / 'installed-linker-seed'
    _manage(manage, 'install-native-linker-seed', '--repo', str(publication),
            '--root', str(linker_seed))
    if not skip('gcc'):
        gcc_workspace = workspace / 'packages/gcc'
        gcc_workspace.mkdir(parents=True)
        produce_gcc_with_native_linker_seed(
            steps['gcc'], workspace=gcc_workspace,
            repository_root=publication, installed_root=linker_seed,
            bootstrap_root=plan.bootstrap_root, source_repository=source,
            manage=manage, jobs=jobs)

    # Restore the exact five individually Manage-published packages, including
    # native GCC. This is an authenticated compiler seed, NOT a runnable native
    # construction provider: Bash and Make are still bootstrap capabilities.
    compiler_seed = workspace / 'installed-compiler-seed'
    _manage(manage, 'install-native-compiler-seed', '--repo', str(publication),
            '--root', str(compiler_seed))
    selected_compiler = authenticate_managed_native_compiler_seed(compiler_seed, publication)
    print('[distro-buildroot] Authenticated five-package Manage compiler seed: '
          + ', '.join(name for name, _version, _arch, _rev in selected_compiler.identities),
          flush=True)
    _smoke_native_compiler_seed(selected_compiler.root)
    authenticate_managed_native_compiler_seed(compiler_seed, publication)

    # There are 19 payload identities; the five above are the foundation.
    # Stage 1B cannot masquerade as a complete native Build provider for the
    # remaining fourteen. Subsequent integration must create and authenticate
    # a Manage-installed provider able to execute these recipes correctly.
    print('[distro-buildroot] Five prerequisite packages published. '
          'Native provider for the remaining fourteen is not implemented; '
          'collection has NOT been completed or promoted.', flush=True)
    raise SelectionError('FS-004 package production incomplete: native provider for remaining fourteen')
