"""FS-004 isolated native package preparation and execution primitives.

This does not publish, install, merge, or assert complete distro-buildroot.
Caller must supply *verified* Stage 1B root and imported capability evidence.
No second recipe runner: run_native_recipe is the existing shared executor.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
import hashlib

from build.selection import Step, SelectionError, _yaml
from build.native_catalog import load_native_catalog
from build.native_manifest import load_native_manifests, plan_selected_native_dependencies
from build.native_recipe_bindings import verify_native_recipe_revision, CATALOG
from build.bootstrap.cross_toolchain import TARGET, prepare_step
from build.bootstrap.cross_chroot_ownership import snapshot_imported_root, require_preserved_imports
from build.native_sandbox import run_native_recipe

# GCC supplements are inherited verbatim from the accepted Stage 1B selection.
STAGE1B = Path(__file__).resolve().parent / 'bootstrap/cross-chroot/lists/cross-chroot.yaml'


@dataclass(frozen=True)
class NativePackageStep:
    step: Step | None
    name: str
    version: str
    recipe: Path
    relationships: tuple[tuple[str, str], ...]
    source_kind: str


def selected_gcc_supplements(path: Path = STAGE1B) -> dict[str, tuple[str, str]]:
    """Read accepted upstream supplement pins; never synthesize checksum bytes."""
    steps = _yaml(path).get('steps')
    if not isinstance(steps, list):
        raise SelectionError('invalid Stage 1B supplement authority')
    matching = [s for s in steps if isinstance(s, dict) and s.get('id') == 'native-gcc'
                and s.get('name') == 'gcc' and s.get('version') == '16.2.0']
    if len(matching) != 1 or set(matching[0].get('supplements', {})) != {'gmp', 'mpfr', 'mpc'}:
        raise SelectionError('missing authoritative Stage 1B GCC supplement pins')
    output = {}
    for name, item in matching[0]['supplements'].items():
        if not isinstance(item, dict) or set(item) != {'version', 'checksum'}:
            raise SelectionError('invalid GCC supplement selection')
        version, digest = item['version'], item['checksum']
        if not isinstance(version, str) or not isinstance(digest, str) or len(digest) != 64:
            raise SelectionError('invalid GCC supplement identity')
        try: int(digest, 16)
        except ValueError as exc: raise SelectionError('invalid GCC supplement checksum') from exc
        output[name] = (version, digest.lower())
    return output


def plan_native_package_steps(repository: Path, revision: str, *,
                              verified_imported: Mapping[str, str]) -> tuple[NativePackageStep, ...]:
    """Plan an immutable recipe/identity schedule; no host or target execution.

    The caller is responsible for authenticating imported capabilities against
    the validated Stage 1B handoff, not merely accepting a declared mapping.
    """
    if not isinstance(verified_imported, Mapping) or not verified_imported:
        raise SelectionError('verified Stage 1B capability mapping required')
    repository = Path(repository).absolute()
    bindings = verify_native_recipe_revision(repository, revision)
    catalog = {s.name: s for s in load_native_catalog(CATALOG)}
    manifests = load_native_manifests()
    plan = plan_selected_native_dependencies(imported=dict(verified_imported))
    by_name = {binding.name: binding for binding in bindings}
    if set(by_name) != set(catalog) or set(manifests) != set(catalog):
        raise SelectionError('native selection/recipe/manifest disagreement')
    supplements = selected_gcc_supplements()
    if set(supplements) != set(manifests['gcc'].supplements):
        raise SelectionError('GCC supplement manifest mismatch')
    result = []
    for name in plan.construction_order:
        selected, binding = catalog[name], by_name[name]
        if (selected.version, selected.checksum) != (binding.version, binding.checksum):
            raise SelectionError('native selection and recipe binding mismatch')
        if selected.kind == 'local':
            step = None
        else:
            step = Step(name, name, selected.version, binding.recipe,
                        selected.checksum, supplements if name == 'gcc' else {})
        result.append(NativePackageStep(step, name, selected.version, binding.recipe,
                                        plan.installed_relationships[name], selected.kind))
    return tuple(result)


def prepare_native_package(step: NativePackageStep, build: Path, cache: Path,
                           repository: Path) -> tuple[Path, Path]:
    """Prepare one verified upstream source or committed Distro local definition."""
    build, cache, repository = Path(build).absolute(), Path(cache).absolute(), Path(repository).absolute()
    if not build.is_dir() or not cache.is_dir() or not cache.is_relative_to(build):
        raise SelectionError('invalid fresh native construction workspace')
    if step.source_kind == 'upstream' and step.step is not None:
        manifest = load_native_manifests()[step.name]
        return prepare_step(step.step, manifest, build, cache)
    if step.name != 'filesystem' or step.source_kind != 'local' or step.step is not None:
        raise SelectionError('unsupported native local source selection')
    # The selected source files live in the verified repository, not this empty
    # source directory. The filesystem Bash recipe does not consume source files.
    location = build / 'steps' / step.name
    if location.exists() or location.is_symlink():
        raise SelectionError('native package workspace already exists')
    source = location / 'source'
    construction = location / 'build'
    source.mkdir(parents=True)
    construction.mkdir()
    return source, construction


def execute_native_package(step: NativePackageStep, build: Path,
                           verified_root: Path, staging: Path, *, jobs: int,
                           source: Path, construction: Path,
                           linux_headers: Path | None = None) -> dict:
    """Execute selected script in shared sandbox and inventory *independent* stage.

    Manage packaging/publication is deliberately absent. The restored root is
    read-only inside the native recipe sandbox, and verified again after return.
    """
    build, verified_root, staging = map(lambda x: Path(x).absolute(),
                                        (build, verified_root, staging))
    source, construction = Path(source).absolute(), Path(construction).absolute()
    if (not staging.is_dir() or staging.is_symlink() or any(staging.iterdir())
            or staging == verified_root or staging == build
            or staging.is_relative_to(verified_root) or staging.is_relative_to(build)
            or not source.is_relative_to(build) or not construction.is_relative_to(build)):
        raise SelectionError('native package stage/source/build directories invalid')
    if not isinstance(jobs, int) or isinstance(jobs, bool) or jobs < 1:
        raise SelectionError('native package parallelism must be positive')
    baseline = snapshot_imported_root(verified_root)
    try:
        run_native_recipe(build, verified_root, staging, step.recipe,
                          source_dir='/work/' + source.relative_to(build).as_posix(),
                          build_dir='/work/' + construction.relative_to(build).as_posix(),
                          package=step.name, version=step.version, step_id=step.name,
                          target=TARGET, jobs=jobs, linux_headers=linux_headers)
    finally:
        require_preserved_imports(verified_root, baseline)
    inventory = snapshot_imported_root(staging)
    if not inventory:
        raise SelectionError(f'{step.name}: native package staged an empty payload')
    return inventory
