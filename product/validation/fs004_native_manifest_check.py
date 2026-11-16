#!/usr/bin/env python3
"""Focused FS-004 Stage 1C manifest projection checks; no regression suite."""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'product/src'))
from build.selection import SelectionError, load_manifests
from build.native_manifest import load_native_manifests, plan_selected_native_dependencies, PACKAGES
from build.native_catalog import VERSIONS

legacy = load_manifests(PACKAGES)
assert legacy['gcc'].dependencies == ('binutils',)
assert legacy['glibc'].dependencies == ('gcc','linux')
assert legacy['linux'].dependencies == ('gcc',)
assert legacy['gcc'].native is not None
native = load_native_manifests()
assert set(native) == set(VERSIONS)
assert all(not m.dependencies for m in native.values())
assert native['gcc'].runtime_dependencies == ('filesystem','glibc','binutils')
assert native['glibc'].build_link_dependencies == ('linux',)
assert native['filesystem'].native is None
# A verified bootstrap provider must be supplied by the eventual controller;
# this fixture is only checking graph mechanics, not claiming verification.
imported={'gcc':'16.2.0','make':'4.4.1','bash':'5.3','binutils':'2.47','linux':'7.1.8'}
plan=plan_selected_native_dependencies(imported=imported)
assert len(plan.construction_order)==13 and len(plan.installed_order)==13
assert plan.installed_order.index('filesystem') < plan.installed_order.index('glibc')
assert plan.installed_order.index('glibc') < plan.installed_order.index('gcc')
assert ('linux','7.1.8') in plan.installed_relationships['glibc']
assert ('binutils','2.47') in plan.installed_relationships['gcc']
assert ('gcc','16.2.0') not in plan.installed_relationships['glibc']
assert len(set(plan.construction_order)) == 13
with TemporaryDirectory() as d:
    dest=Path(d)
    for original in PACKAGES.glob('*.yaml'):
        (dest/original.name).write_bytes(original.read_bytes())
    bad=dest/'gcc.yaml'
    doc=yaml.safe_load(bad.read_text())
    del doc['native']
    bad.write_text(yaml.safe_dump(doc))
    try:load_native_manifests(dest)
    except SelectionError:pass
    else:raise AssertionError('unclassified selected GCC accepted')
    doc=yaml.safe_load((PACKAGES/'gcc.yaml').read_text())
    doc['native']['runtime_dependencies']=['glibc','not-selected']
    bad.write_text(yaml.safe_dump(doc))
    try:plan_selected_native_dependencies(directory=dest, imported=imported)
    except SelectionError:pass
    else:raise AssertionError('unknown installed dependency accepted')
print('PASS FS-004 targeted native manifest classification')
