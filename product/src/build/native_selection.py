"""FS-004 exact dependency planning, distinct from legacy Stage 1A/1B order checks.

This module does not install, publish, or claim Stage 1C closure. The full
Stage 1C package list and local-source provenance machinery follow in later
Build slices. Install edges are exclusively manifest-authoritative.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
from build.selection import Manifest, SelectionError

@dataclass(frozen=True)
class NativeDependencyPlan:
    construction_order: tuple[str, ...]
    installed_order: tuple[str, ...]
    installed_relationships: dict[str, tuple[tuple[str, str], ...]]


def _toposort(graph: dict[str, set[str]]) -> tuple[str, ...]:
    """Stable, deterministic order with explicit cycle diagnostics."""
    remaining = {k: set(v) for k, v in graph.items()}
    ordered = []
    while remaining:
        ready = sorted(k for k, v in remaining.items() if not v)
        if not ready:
            raise SelectionError("cyclic dependency graph: " + ", ".join(sorted(remaining)))
        for name in ready:
            ordered.append(name)
            del remaining[name]
        for deps in remaining.values():
            deps.difference_update(ready)
    return tuple(ordered)


def resolve_native_dependencies(
    selected: Mapping[str, str], manifests: Mapping[str, Manifest],
    *, imported: Mapping[str, str] | None = None,
) -> NativeDependencyPlan:
    """Resolve distinct construction and install graphs for exact selections.

    `imported` is a caller-verified bootstrap capability set, never a source
    of final installed relationships. Callers must validate its provenance.
    """
    imported = {} if imported is None else imported
    if not isinstance(selected, Mapping) or not selected or not isinstance(imported, Mapping):
        raise SelectionError("invalid native package selection/imported capabilities")
    from build.selection import _name, _version
    if any(not _name(n) or not _version(v) or n not in manifests for n, v in selected.items()):
        raise SelectionError("invalid or unknown exact package selection")
    if any(not _name(n) or not _version(v) or n not in manifests for n, v in imported.items()):
        raise SelectionError("invalid imported capability identity")
    if any(n in imported and imported[n] != v for n, v in selected.items()):
        raise SelectionError("selected/imported package version conflict")
    build_graph = {name: set() for name in selected}
    install_graph = {name: set() for name in selected}
    relationships = {}
    for name in sorted(selected):
        manifest = manifests[name]
        if manifest.dependencies:
            raise SelectionError(f"{name}: legacy dependencies require explicit FS-004 classification")
        build_needs = set(manifest.build_tools) | set(manifest.build_link_dependencies)
        installed_needs = set(manifest.build_link_dependencies) | set(manifest.runtime_dependencies)
        if name in build_needs | installed_needs:
            raise SelectionError(f"{name}: self-dependency")
        # Build tools/link prerequisites may come from the verified Stage 1B
        # provider during Bootstrap; installed relationships never may.
        for dep in build_needs:
            if dep in imported:
                continue
            if dep not in selected:
                raise SelectionError(f"{name}: missing construction prerequisite {dep}")
            build_graph[name].add(dep)
        for dep in installed_needs:
            if dep not in selected:
                raise SelectionError(f"{name}: missing installed prerequisite {dep}")
            install_graph[name].add(dep)
        relationships[name] = tuple((dep, selected[dep]) for dep in sorted(installed_needs))
    return NativeDependencyPlan(_toposort(build_graph), _toposort(install_graph), relationships)
