"""FS-003 required product mechanical evaluation; not a regression suite.

These bounded contracts run without network access or rebuilding the toolchain.
The qualified-host native build/publish log remains separately reviewed evidence.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'product/src'


def _check(code: str) -> bool:
    env = {'PATH': os.defpath, 'PYTHONPATH': str(SRC), 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                            env=env, capture_output=True, text=True)
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr)
    return result.returncode == 0


def invocation_selection_contract() -> bool:
    """NR-001,004: selected native package and existing Build entry point."""
    return _check('''
from build.bootstrap.cross_toolchain import PACKAGES
from build.bootstrap.distro_buildroot import STAGE
from build.selection import load_manifests,select_steps
from pathlib import Path
import subprocess,sys
manifests=load_manifests(PACKAGES)
steps=select_steps(STAGE/'lists/distro-buildroot.yaml',manifests,STAGE)
assert [(s.id,s.name,s.version,s.checksum) for s in steps]==[('sed','sed','4.10','b8e72182b2ec96a3574e2998c47b7aaa64cc20ce000d8e9ac313cc07cecf28c7')]
assert steps[0].recipe==STAGE/'recipes/sed.sh'
assert not manifests['sed'].dependencies
assert not hasattr(manifests['sed'],'version')
script=steps[0].recipe.read_text()
assert '"$DISTRO_SOURCE_DIR/configure"' in script and 'DESTDIR="$DISTRO_ROOT_DIR"' in script
assert 'make -j"$DISTRO_JOBS"' in script
p=subprocess.run([sys.executable,'-B','-m','build.cli','distro-buildroot','--help'],capture_output=True,text=True)
assert p.returncode==0 and '--cross-chroot' in p.stdout and '--root' in p.stdout
''')


def import_workspace_contract() -> bool:
    """NR-002,003: rejected unverified imports and separated Build roles."""
    return _check('''
from pathlib import Path
from tempfile import TemporaryDirectory
import inspect
from build.bootstrap.distro_buildroot_import import restore_cross_chroot,BuildrootImportError
from build.bootstrap import distro_buildroot
with TemporaryDirectory(prefix='fs003-import-') as d:
    base=Path(d); dest=base/'root'; dest.mkdir(); archive=base/'cross-chroot.tar.xz'
    for create in (False,True):
        if create:archive.write_bytes(b'not an archive')
        try:restore_cross_chroot(archive,dest)
        except BuildrootImportError:pass
        else:raise AssertionError('unverified Stage 1B input accepted')
        assert not list(dest.iterdir())
src=inspect.getsource(distro_buildroot.run_stage)
for name in ('restore_cross_chroot(archive, imported)','root / "build"','root / "root"','root / "staging"',
             'root / "exchange"','root / "repository"','require_preserved_imports(imported, baseline)'):
    assert name in src,name
''')


def native_staging_contract() -> bool:
    """NR-005,006,012: target-only native command, isolated stage, runtime gate."""
    return _check('''
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import inspect
from build.native_sandbox import native_recipe_command,verify_staged_sed
from build.bootstrap.distro_buildroot import STAGE,run_stage
with TemporaryDirectory(prefix='fs003-native-') as d:
    base=Path(d);work=base/'work';root=base/'root';stage=base/'stage'
    for path in (work,root,stage):path.mkdir()
    for name in ('source','build'):(work/name).mkdir()
    with patch('build.native_sandbox._bwrap',return_value='/usr/bin/bwrap'):
        cmd=native_recipe_command(work,root,stage,STAGE/'recipes/sed.sh',source_dir='/work/source',build_dir='/work/build',package='sed',version='4.10',step_id='sed',target='x86_64-distro-linux-gnu')
    assert ['--ro-bind',str(root),'/']==cmd[cmd.index(str(root))-1:cmd.index(str(root))+2]
    assert ['--bind',str(stage),'/install']==cmd[cmd.index(str(stage))-1:cmd.index(str(stage))+2]
    assert ['--tmpfs','/recipe'] == cmd[cmd.index('/recipe')-1:cmd.index('/recipe')+1]
    assert '--unshare-net' in cmd and '--clearenv' in cmd
    assert not any(value in cmd for value in ('/toolchain','/usr/lib','/usr/bin'))
source=inspect.getsource(run_stage)
assert 'run_native_recipe(' in source and 'verify_staged_sed(' in source
assert 'snapshot_imported_root(package_stage)' in source
assert 'require_preserved_imports(imported, baseline)' in source
runtime=inspect.getsource(verify_staged_sed)
assert 'subprocess.run' in runtime and '--ro-bind' in runtime and 's/foo/bar/' in runtime
''')


def package_creation_contract() -> bool:
    """NR-007,008: immutable selection and verified independent payload archive."""
    return _check('''
from pathlib import Path
from tempfile import TemporaryDirectory
from manage.package import create,verify,restore,PackageError,_json_bytes
from build.bootstrap.distro_buildroot import run_stage
import inspect
src=inspect.getsource(run_stage)
for part in ('"architecture": "x86_64", "revision": 1','"relationships": []','"selection.json"','"create"','"publish"','"verify-repo"'):
    assert part in src,part
with TemporaryDirectory(prefix='fs003-package-') as d:
    base=Path(d);exchange=base/'exchange';payload=exchange/'payload';payload.mkdir(parents=True)
    target=payload/'usr/bin/sed';target.parent.mkdir(parents=True);target.write_bytes(b'example package data')
    identity={'name':'sed','version':'4.10','architecture':'x86_64','revision':1}
    (exchange/'selection.json').write_bytes(_json_bytes({'schema_version':1,'identity':identity,'relationships':[]}))
    package=create('sed',exchange)
    metadata=verify(package)
    assert metadata['identity']==identity and metadata['relationships']==[]
    assert [e['path'] for e in metadata['paths']]==['usr/bin/sed']
    restored=base/'restored';restored.mkdir()
    restore(package,restored)
    assert (restored/'usr/bin/sed').read_bytes()==b'example package data'
    try:create('different',exchange)
    except PackageError:pass
    else:raise AssertionError('mismatched identity accepted')
''')


def publication_integrity_contract() -> bool:
    """NR-009,010,011: verified publication, path authority, failure integrity."""
    return _check('''
from pathlib import Path
from tempfile import TemporaryDirectory
from manage.package import create,verify,restore,PackageError,_json_bytes
from manage.repository import publish,verify_repository
from unittest.mock import patch
with TemporaryDirectory(prefix='fs003-publish-') as d:
    root=Path(d);e=root/'exchange';p=e/'payload';p.mkdir(parents=True)
    f=p/'usr/bin/sed';f.parent.mkdir(parents=True);f.write_bytes(b'synthetic content')
    selection={'schema_version':1,'identity':{'name':'sed','version':'4.10','architecture':'x86_64','revision':1},'relationships':[]}
    (e/'selection.json').write_bytes(_json_bytes(selection))
    artifact=create('sed',e)
    repo=root/'repo';repo.mkdir()
    # The Cygwin validation backend cannot fsync this repository file.
    # Exercise index ordering and integrity; Linux host evidence covers fsync.
    with patch('manage.repository.os.fsync', return_value=None):
        published=publish('sed',repo,e)
    assert published.is_file() and verify_repository(repo)['packages'][0]['identity']==selection['identity']
    previous=(repo/'index.json').read_bytes()
    try:
        with patch('manage.repository.os.fsync', return_value=None):
            publish('sed',repo,e)
    except PackageError:pass
    else:raise AssertionError('published identity silently replaced')
    assert (repo/'index.json').read_bytes()==previous
    assert verify_repository(repo)['packages'][0]['artifact']['size_bytes']==published.stat().st_size
    independent=root/'independent';independent.mkdir()
    restore(published,independent)
    assert (independent/'usr/bin/sed').read_bytes()==b'synthetic content'
    assert not (repo/'.publish.lock').exists()
''')


def traceability_contract() -> bool:
    """NR-013: all thirteen active mechanical requirements bound to required tasks."""
    from validate_product import TASKS
    text=(ROOT/'product/specs/FS-003-stage1c-initial-native-package.md').read_text()
    bindings=json.loads((ROOT/'product/validation/requirement-evaluation.json').read_text())['bindings']
    required={f'FS-003-NR-{number:03d}' for number in range(1,14)}
    active=set()
    for section in re.split(r'(?=^### FS-003-NR-\d{3})',text,flags=re.M):
        match=re.match(r'### (FS-003-NR-\d{3})',section)
        if not match or match.group(1) not in required:continue
        if '**State: Inactive**' in section:return False
        if not any(f'**Classification: {value}**' in section for value in ('M','B')):return False
        active.add(match.group(1))
    if active!=required:return False
    bound={item['requirement']:item['tasks'] for item in bindings}
    return all(name in bound and bound[name] and
               all(task in TASKS and task.startswith('fs003-') for task in bound[name])
               for name in required)
