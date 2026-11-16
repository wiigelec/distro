#!/usr/bin/env python3
"""Targeted FS-004 Build/controller exchange checks, no regression suite."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'product/src'))
from build.native_package_execution import NativePackageStep
from build.native_collection_controller import (_selection, _write_selection,
    CollectionPlan, require_collection_provider, prepare_collection)
from build.selection import SelectionError

step=NativePackageStep(None,'gcc','16.2.0',Path('gcc.sh'),
                       (('binutils','2.47'),('filesystem','1'),('glibc','2.44')),'upstream')
selected=_selection(step)
assert selected['identity']=={'name':'gcc','version':'16.2.0','architecture':'x86_64','revision':1}
assert selected['relationships']==[{'name':'binutils','version':'2.47'},
                                  {'name':'filesystem','version':'1'},
                                  {'name':'glibc','version':'2.44'}]
with TemporaryDirectory() as temporary:
    root=Path(temporary)
    exchange=root/'exchange'; exchange.mkdir()
    _write_selection(exchange,step)
    assert json.loads((exchange/'selection.json').read_text())==selected
    assert (exchange/'selection.json').read_bytes().endswith(b'\n')
    try:prepare_collection(exchange,root/'cross-chroot.tar.xz',root,'0'*40)
    except SelectionError:pass
    else:raise AssertionError('nonempty workspace accepted')
    plan=CollectionPlan('a'*64,(step,),root)
    try:require_collection_provider(plan)
    except SelectionError as exc:
        assert 'Manage-installed' in str(exc)
    else:raise AssertionError('bootstrap root accepted as complete native root')
    bad=NativePackageStep(None,'gcc','16.2.0',Path('gcc.sh'),
                          (('glibc','2.44'),('binutils','2.47')),'upstream')
    try:_selection(bad)
    except SelectionError:pass
    else:raise AssertionError('unordered installed relationships accepted')
print('PASS FS-004 targeted native collection controller contracts')
