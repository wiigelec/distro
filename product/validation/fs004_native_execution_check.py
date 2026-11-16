#!/usr/bin/env python3
"""FS-004 targeted isolated-package execution contract; not a regression suite."""
from __future__ import annotations
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'product/src'))
from build.selection import SelectionError
from build.native_package_execution import (NativePackageStep, selected_gcc_supplements,
    prepare_native_package, execute_native_package)
assert set(selected_gcc_supplements()) == {'gmp','mpfr','mpc'}
with TemporaryDirectory() as folder:
    root=Path(folder)
    build=root/'build'; build.mkdir()
    cache=build/'sources'; cache.mkdir()
    imported=root/'imported'; imported.mkdir()
    stage=root/'staging'; stage.mkdir()
    step=NativePackageStep(None,'filesystem','1',Path('filesystem.sh'),(), 'local')
    source,construction=prepare_native_package(step,build,cache,root)
    assert source.is_dir() and construction.is_dir()
    try:prepare_native_package(step,build,cache,root)
    except SelectionError:pass
    else:raise AssertionError('native package reused workspace')
    def fake_executor(work,provider,dest,recipe,**kwargs):
        assert work==build and provider==imported and dest==stage
        assert kwargs['package']=='filesystem' and kwargs['target']=='x86_64-distro-linux-gnu'
        assert kwargs['source_dir'].startswith('/work/steps/filesystem/')
        (stage/'etc').mkdir()
        (stage/'etc'/'issue').write_text('target-only staging\n')
    with patch('build.native_package_execution.run_native_recipe', side_effect=fake_executor):
        output=execute_native_package(step,build,imported,stage,jobs=1,
                                      source=source,construction=construction)
    assert 'etc/issue' in output and output['etc/issue'][0]=='file'
    assert not list(imported.iterdir())
print('PASS FS-004 targeted native execution primitives')
