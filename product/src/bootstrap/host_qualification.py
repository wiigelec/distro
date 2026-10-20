#!/usr/bin/env python3
"""Fail-closed foreign-host qualification and immutable package baseline.

This module deliberately does NOT build a toolchain, fetch sources, or change
host packages. Upstream counterparts are provided as reviewed manifest inputs;
source artifact authentication happens on first consumption in later work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

SCHEMA = 1
ARCH_VERSION = re.compile(r"^(?:(?P<epoch>[0-9]+):)?(?P<upstream>.+)-(?P<release>[^-]+)$")


class QualificationError(Exception):
    pass


def parse_arch_version(value: str) -> dict[str, str | None]:
    match = ARCH_VERSION.fullmatch(value)
    if not match or not match['upstream'] or not match['release']:
        raise QualificationError(f"invalid Arch package version: {value!r}")
    return {'full': value, 'epoch': match['epoch'], 'pkgver': match['upstream'], 'pkgrel': match['release']}


def run_command(argv: list[str]) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30,
                            env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, check=False)
    if result.returncode:
        raise QualificationError(f"command failed ({result.returncode}): {' '.join(argv)}: {result.stderr.strip()[:250]}")
    return result.stdout.strip()


def installed_arch_packages() -> dict[str, str]:
    inventory = {}
    for line in run_command(['pacman', '-Q']).splitlines():
        fields = line.split()
        if len(fields) != 2 or fields[0] in inventory:
            raise QualificationError(f"unexpected pacman -Q row: {line!r}")
        inventory[fields[0]] = fields[1]
    if not inventory:
        raise QualificationError('empty installed Arch package inventory')
    return inventory


def qualify(manifest: dict, installed: dict[str, str]) -> dict:
    """Require explicit mapping for every entry in the already-closed manifest.

    The schema separates installed host package, upstream source and Distro
    package identities, including split-package mappings. No heuristic mapping
    from pacman pkgver to upstream release is accepted as verification.
    """
    if manifest.get('schema_version') != SCHEMA:
        raise QualificationError('unsupported manifest schema')
    packages = manifest.get('packages')
    if not isinstance(packages, list) or not packages:
        raise QualificationError('a nonempty complete package closure is required')
    if manifest.get('closure_complete') is not True:
        raise QualificationError('manifest must declare its reviewed bootstrap dependency closure complete')
    results = []
    seen = set()
    for package in packages:
        name = package.get('distro_name')
        host = package.get('host_package')
        source = package.get('upstream')
        if not isinstance(name, str) or not name or name in seen:
            raise QualificationError('duplicate or missing Distro package identity')
        seen.add(name)
        if not isinstance(host, str) or not host or host not in installed:
            raise QualificationError(f'{name}: required installed host counterpart {host!r} missing')
        if not isinstance(source, dict) or not all(isinstance(source.get(k), str) and source[k] for k in ('name', 'version', 'official_url', 'mapping_basis')):
            raise QualificationError(f'{name}: explicit reviewed upstream identity and mapping evidence required')
        if not source['official_url'].startswith('https://'):
            raise QualificationError(f'{name}: official upstream source location must use HTTPS')
        results.append({'distro_name': name, 'host_package': host,
                        'host_version': parse_arch_version(installed[host]),
                        'upstream': source})
    payload = {'schema_version': SCHEMA, 'host_kind': 'arch', 'status': 'qualified-mapping-baseline',
               'packages': sorted(results, key=lambda item: item['distro_name'])}
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    payload['baseline_sha256'] = hashlib.sha256(canonical).hexdigest()
    return payload


def save_new(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = (json.dumps(data, indent=2, sort_keys=True) + '\n').encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise QualificationError('baseline already exists; never overwrite a frozen execution') from exc
    with os.fdopen(fd, 'wb') as stream:
        stream.write(blob)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        if os.geteuid() == 0:
            raise QualificationError('run as an unprivileged user')
        manifest = json.loads(args.manifest.read_text())
        result = qualify(manifest, installed_arch_packages())
        save_new(args.output, result)
        print(f"qualified {len(result['packages'])} components; baseline {result['baseline_sha256']}")
        return 0
    except (QualificationError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f'Host qualification blocked: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
