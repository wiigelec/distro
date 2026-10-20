"""Validate a finite package inventory and its declared dependency closure.

This module verifies the structure and internal reachability of an inventory.
It does not discover missing dependencies from package recipes or the host.
"""
from __future__ import annotations

from collections import deque


class ClosureError(ValueError):
    """A selected package inventory is incomplete or internally inconsistent."""


def resolve_closure(manifest: dict) -> dict:
    """Validate package identities, build/runtime edges, roots, and reviewed cycle breaks.

    An explicit finite inventory is required. A graph can be internally closed
    while omitting a real dependency; callers must independently establish the
    inventory from recipes and source evidence before treating it as complete.
    """
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
        raise ClosureError('unsupported inventory schema')
    records = manifest.get('packages')
    roots = manifest.get('roots')
    if not isinstance(records, list) or not records:
        raise ClosureError('nonempty package inventory required')
    if not isinstance(roots, list) or not roots or len(set(roots)) != len(roots) or not all(isinstance(x, str) and x for x in roots):
        raise ClosureError('nonempty unique package roots required')
    by_name = {}
    for record in records:
        if not isinstance(record, dict):
            raise ClosureError('package entry must be an object')
        name = record.get('distro_name')
        if not isinstance(name, str) or not name or name in by_name:
            raise ClosureError('missing or duplicate package identity')
        for field in ('build_dependencies', 'runtime_dependencies'):
            values = record.get(field)
            if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values) or len(set(values)) != len(values):
                raise ClosureError(f'{name}: {field} must be a unique list of package identities')
        by_name[name] = record
    if any(root not in by_name for root in roots):
        raise ClosureError('root package missing from inventory')
    edges = {name: sorted(set(record['build_dependencies'] + record['runtime_dependencies'])) for name, record in by_name.items()}
    for name, deps in edges.items():
        for dep in deps:
            if dep not in by_name:
                raise ClosureError(f'{name}: unresolved dependency {dep}')
    reached = set(roots)
    queue = deque(sorted(roots))
    while queue:
        for child in edges[queue.popleft()]:
            if child not in reached:
                reached.add(child)
                queue.append(child)
    orphaned = sorted(set(by_name) - reached)
    if orphaned:
        raise ClosureError(f'unreachable packages in selected inventory: {", ".join(orphaned)}')

    # Tarjan SCC; any dependency cycle must be explicitly reviewed as a group.
    counter = 0
    stack = []
    on_stack = set()
    indices = {}
    low = {}
    cycles = []
    def visit(node):
        nonlocal counter
        indices[node] = low[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in edges[node]:
            if nxt not in indices:
                visit(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on_stack:
                low[node] = min(low[node], indices[nxt])
        if low[node] == indices[node]:
            members = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                members.append(member)
                if member == node:
                    break
            if len(members) > 1 or node in edges[node]:
                cycles.append(tuple(sorted(members)))
    for node in sorted(by_name):
        if node not in indices:
            visit(node)
    declared = manifest.get('reviewed_cycle_breaks', [])
    if not isinstance(declared, list):
        raise ClosureError('reviewed_cycle_breaks must be a list')
    reviewed = set()
    for item in declared:
        if not isinstance(item, dict) or not isinstance(item.get('packages'), list) or not isinstance(item.get('reason'), str) or not item['reason'].strip():
            raise ClosureError('cycle break requires packages and reviewed reason')
        members = item['packages']
        if not members or any(not isinstance(x, str) or not x for x in members) or len(set(members)) != len(members):
            raise ClosureError('cycle break packages must be unique identities')
        key = tuple(sorted(members))
        if key in reviewed:
            raise ClosureError('duplicate cycle break')
        reviewed.add(key)
    detected = set(cycles)
    if detected != reviewed:
        raise ClosureError('dependency cycles must match explicit reviewed cycle breaks')
    return {'packages': sorted(by_name), 'roots': sorted(roots), 'dependency_edges': sum(map(len, edges.values())),
            'reviewed_cycles': [list(c) for c in sorted(detected)]}
