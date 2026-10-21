"""Inspect availability of selected cross-toolchain source inputs.

Discovery is evidence, not authentication or permission to construct.
"""
from __future__ import annotations

SOURCE_OWNERS = ('binutils', 'gcc', 'linux-api-headers', 'glibc')


def evaluate_inputs(audit: dict) -> dict:
    """Report required source owners not available from the host audit.

    libstdc++ consumes the GCC source already identified for the compiler.
    """
    selected = {}
    for item in audit.get('packages', []):
        name = item.get('distro_name')
        if not isinstance(name, str) or name in selected:
            raise ValueError('missing or duplicate audited package identity')
        selected[name] = item
    entries = []
    for name in SOURCE_OWNERS:
        item = selected.get(name)
        if item is None:
            entries.append({'name': name, 'status': 'not-in-selected-manifest',
                            'reason': 'source owner absent from selected inventory'})
            continue
        discovery = item.get('upstream_discovery') or {}
        source = discovery.get('upstream') or {}
        if discovery.get('status') != 'candidate-exact-match' or not source.get('artifact_url'):
            entries.append({'name': name, 'status': 'unresolved',
                            'reason': discovery.get('reason', 'source discovery incomplete')})
            continue
        entries.append({'name': name, 'status': 'candidate-discovered',
                        'source_version': source.get('version'),
                        'artifact_url': source['artifact_url']})
    blocked = [entry['name'] for entry in entries if entry['status'] != 'candidate-discovered']
    return {'status': 'discovery-incomplete' if blocked else 'discovered-not-qualified',
            'required_source_owners': list(SOURCE_OWNERS), 'sources': entries,
            'missing_or_unresolved': blocked,
            'note': 'Source candidates are not verified archives or a qualified execution baseline.'}
