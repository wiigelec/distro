"""Generate non-authoritative mapping candidates from an Arch discovery snapshot.

Suggestions always require independent upstream/source/dependency review.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path


def candidates(report: dict, names: list[str]) -> dict:
    installed = {}
    for line in report['commands']['installed_packages']['stdout'].splitlines():
        fields = line.split()
        if len(fields) != 2 or fields[0] in installed:
            raise ValueError('invalid installed package inventory')
        installed[fields[0]] = fields[1]
    results = []
    for name in sorted(set(names)):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.-]*', name):
            raise ValueError('invalid candidate identity')
        version = installed.get(name)
        candidate = None
        if version is not None:
            stem = version.rsplit('-', 1)[0]
            candidate = stem.split(':', 1)[-1]
        results.append({'distro_name': name, 'host_package_candidate': name,
                        'host_version_observed': version,
                        'upstream_version_candidate_unverified': candidate,
                        'review_status': 'unreviewed',
                        'upstream_source': None, 'build_dependencies': None,
                        'runtime_dependencies': None, 'mapping_evidence': None})
    return {'schema_version': 1, 'status': 'unreviewed-candidates',
            'closure_complete': False, 'packages': results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-report', type=Path, required=True)
    parser.add_argument('--names', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(candidates(json.loads(args.host_report.read_text()),
                                                  args.names), indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
