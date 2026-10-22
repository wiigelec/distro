"""Qualify a complete package inventory before starting toolchain construction.

The inventory is caller-reviewed: validating it cannot discover dependencies
that were omitted from build recipes or platform requirements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from dependency_closure import ClosureError, resolve_closure
from host_qualification import QualificationError, installed_arch_packages, qualify, save_new
from host_checks import HostCheckError, qualify_execution_host, qualify_source_availability


class PreflightError(ValueError):
    """The selected inventory cannot form a qualified source baseline."""


def canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode('utf-8')).hexdigest()


def qualified_baseline(manifest: dict, installed: dict[str, str]) -> dict:
    """Resolve graph and every package-to-host-to-upstream correspondence together.

    Build/runtime edges and source mapping must share one inventory; otherwise
    a graph change could evade the original host-qualification boundary.
    """
    if not isinstance(manifest, dict) or manifest.get('closure_complete') is not True:
        raise PreflightError('complete, reviewed package inventory required')
    try:
        closure = resolve_closure(manifest)
        mapped = qualify(manifest, installed)
    except (ClosureError, QualificationError, KeyError, TypeError, ValueError) as exc:
        raise PreflightError(str(exc)) from exc
    from source_artifacts import source_spec
    for component in mapped['packages']:
        try:
            source_spec(component['upstream'])
        except (ValueError, TypeError) as exc:
            raise PreflightError(f"{component['distro_name']}: {exc}") from exc
    if set(closure['packages']) != {item['distro_name'] for item in mapped['packages']}:
        raise PreflightError('graph and qualified mapping inventories differ')
    # Preserve the declared graph itself, not merely its counts.
    graph = [{'distro_name': record['distro_name'],
              'build_dependencies': sorted(record['build_dependencies']),
              'runtime_dependencies': sorted(record['runtime_dependencies'])}
             for record in manifest['packages']]
    roots = sorted(manifest['roots'])
    mapped.pop('baseline_sha256', None)
    result = {
        **mapped,
        'status': 'qualified-mapping-baseline',
        'inventory': sorted(graph, key=lambda record: record['distro_name']),
        'roots': roots,
        'reviewed_cycle_breaks': manifest.get('reviewed_cycle_breaks', []),
        'closure_summary': closure,
        'inventory_sha256': canonical_digest(manifest),
    }
    result['baseline_sha256'] = canonical_digest(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Freeze a complete qualified host/source inventory')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args(argv)
    try:
        import os
        if os.geteuid() == 0:
            raise PreflightError('run as an unprivileged user')
        manifest = json.loads(options.manifest.read_text(encoding='utf-8'))
        qualified = qualified_baseline(manifest, installed_arch_packages())
        host_report = qualify_execution_host()
        source_report = qualify_source_availability(qualified['packages'])
        qualified.pop('baseline_sha256')
        qualified['host_execution'] = host_report
        qualified['source_availability'] = source_report
        qualified['baseline_sha256'] = canonical_digest(qualified)
        save_new(options.output, qualified)
        print(f"qualified {len(qualified['packages'])} packages: {qualified['baseline_sha256']}")
        return 0
    except (PreflightError, QualificationError, HostCheckError, OSError, ValueError) as exc:
        print(f'Host qualification blocked: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
