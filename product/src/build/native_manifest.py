"""FS-004 explicit native dependency projection from authoritative manifests.

No synthetic dependencies, no inferred installed links, no execution.
Legacy Stage 1A/B/FS-003 consumers continue to see their original fields.
This selection alone is not a verified package collection or closure proof.
"""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from build.selection import Manifest, SelectionError, load_manifests
from build.native_catalog import VERSIONS, load_native_catalog
from build.native_selection import NativeDependencyPlan, resolve_native_dependencies

PACKAGES = Path(__file__).resolve().parent / 'packages'
CATALOG = Path(__file__).resolve().parent / 'bootstrap/distro-buildroot/lists/native-sources.yaml'


def load_native_manifests(directory: Path = PACKAGES) -> dict[str, Manifest]:
    """Explicitly project FS-004 categories from each unique source manifest."""
    manifests = load_manifests(directory)
    if set(VERSIONS) - set(manifests):
        raise SelectionError('missing Stage 1C source manifest')
    selected: dict[str, Manifest] = {}
    for name in VERSIONS:
        manifest = manifests[name]
        if manifest.native is None:
            if name != 'filesystem':
                raise SelectionError(f'{name}: missing explicit native classification')
            # Filesystem's top-level categorized fields are already Stage 1C-only.
            if manifest.dependencies:
                raise SelectionError('filesystem cannot carry legacy dependencies')
            selected[name] = manifest
        else:
            if name == 'filesystem':
                raise SelectionError('filesystem must use its existing direct categories')
            if manifest.build_tools or manifest.build_link_dependencies or manifest.runtime_dependencies:
                raise SelectionError(f'{name}: competing native category authority')
            categories = manifest.native
            selected[name] = replace(
                manifest, dependencies=(),
                build_tools=categories.build_tools,
                build_link_dependencies=categories.build_link_dependencies,
                runtime_dependencies=categories.runtime_dependencies,
                native=None,
            )
    return selected


def plan_selected_native_dependencies(*, imported: dict[str, str] | None = None,
                                     directory: Path = PACKAGES,
                                     catalog_path: Path = CATALOG) -> NativeDependencyPlan:
    """Plan construction/install graphs without constructing or installing."""
    chosen = load_native_catalog(catalog_path)
    if {p.name:p.version for p in chosen} != VERSIONS:
        raise SelectionError('native manifest/catalog identity mismatch')
    manifests = load_native_manifests(directory)
    for p in chosen:
        if manifests[p.name].source.kind != p.kind:
            raise SelectionError(f'{p.name}: selected source kind mismatch')
    return resolve_native_dependencies(
        {p.name:p.version for p in chosen}, manifests, imported=imported,
    )
