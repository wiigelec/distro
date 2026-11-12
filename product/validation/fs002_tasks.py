"""FS-002 mechanical contract checks; no toolchain rebuild or network access.

Functional/relocation completion is independently evidenced by a qualified host
run; this module checks the implementation contracts and failure boundaries.
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
    completed = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                               env=env, text=True, capture_output=True)
    if completed.returncode:
        print(completed.stderr or completed.stdout, file=sys.stderr)
    return completed.returncode == 0


def invocation_selection_contract() -> bool:
    """NR-001,004,005,007: CLI, manifest/list identity and imported prerequisites."""
    return _check('''
import subprocess,sys
from build.bootstrap.cross_toolchain import PACKAGES
from build.bootstrap.cross_chroot import STAGE
from build.selection import load_manifests,select_steps,SelectionError
m=load_manifests(PACKAGES)
steps=select_steps(STAGE/'lists/cross-chroot.yaml',m,STAGE,imported={'binutils':'2.47'})
expected=[('bash','bash','5.3'),('coreutils','coreutils','9.10'),
 ('sed','sed','4.10'),('grep','grep','3.12'),('gawk','gawk','5.4.0'),
 ('make','make','4.4.1'),('diffutils','diffutils','3.12'),('tar','tar','1.35'),
 ('native-binutils','binutils','2.47'),('native-gcc','gcc','16.2.0')]
assert [(s.id,s.name,s.version) for s in steps]==expected
assert len({s.id for s in steps})==10
assert all(s.recipe.is_file() and s.recipe.suffix=='.sh' and len(s.checksum)==64 for s in steps)
assert set(steps[-1].supplements)=={'gmp','mpfr','mpc'}
assert all(not hasattr(v,'version') and not hasattr(v,'recipe') for v in m.values())
# The full list builds native Binutils before native GCC, so an empty imported
# prerequisite map is valid for that list. Test actual missing dependency by
# selecting GCC alone, with no earlier Binutils step and no imported capability.
from tempfile import TemporaryDirectory
from pathlib import Path
import yaml
with TemporaryDirectory(prefix='fs002-missing-dep-') as temp:
    isolated_list=Path(temp)/'gcc-only.yaml'
    original=yaml.safe_load((STAGE/'lists/cross-chroot.yaml').read_text())
    isolated_list.write_text(yaml.safe_dump({'steps':[original['steps'][-1]]}))
    try: select_steps(isolated_list,m,STAGE,imported={})
    except SelectionError: pass
    else: raise AssertionError('GCC without Binutils prerequisite accepted')
# A conflicting imported version must also fail, even when the selected list
# contains a later native Binutils construction step.
try: select_steps(STAGE/'lists/cross-chroot.yaml',m,STAGE,imported={'binutils':'2.46'})
except SelectionError: pass
else: raise AssertionError('mismatched imported Binutils version accepted')
p=subprocess.run([sys.executable,'-B','-m','build.cli','cross-chroot','--help'],capture_output=True,text=True)
assert p.returncode==0 and '--root' in p.stdout and '--cross-toolchain' in p.stdout
''')


def import_contract() -> bool:
    """NR-002,003,007: reject partial handoffs and mismatched imported capability."""
    return _check('''
from pathlib import Path
from tempfile import TemporaryDirectory
from build.bootstrap.cross_chroot_import import restore_cross_toolchain,CrossChrootImportError
from build.bootstrap.cross_chroot_prerequisites import imported_prerequisites,ImportedPrerequisiteError
from build.bootstrap.cross_toolchain import TARGET
with TemporaryDirectory(prefix='fs002-import-') as d:
    base=Path(d); root=base/'root'; root.mkdir()
    def reject(fn,typ):
        try: fn()
        except typ: return
        raise AssertionError('invalid handoff accepted')
    archive=base/'cross-toolchain.tar.xz'
    reject(lambda:restore_cross_toolchain(archive,root),CrossChrootImportError)
    archive.write_bytes(b'incomplete')
    reject(lambda:restore_cross_toolchain(archive,root),CrossChrootImportError)
    (base/'cross-toolchain.json').write_text('{}')
    reject(lambda:restore_cross_toolchain(archive,root),CrossChrootImportError)
    assert not list(root.iterdir())
    metadata={'toolchain':{'target':TARGET,'sysroot':'/toolchain','tools_prefix':'/toolchain/tools'},
              'sources':[{'package':'binutils','version':'2.47','sha256':'a'*64}]}
    reject(lambda:imported_prerequisites(metadata,root),ImportedPrerequisiteError)
    b=root/'tools/bin'; b.mkdir(parents=True)
    for name in (TARGET+'-as',TARGET+'-ld'): (b/name).write_bytes(b'present')
    assert imported_prerequisites(metadata,root)=={'binutils':'2.47'}
    metadata['toolchain']['sysroot']='/wrong'
    reject(lambda:imported_prerequisites(metadata,root),ImportedPrerequisiteError)
''')


def sandbox_install_contract() -> bool:
    """NR-006,008,009: direct Bash sandbox wiring and collision refusal."""
    return _check('''
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from build.bootstrap.cross_chroot_sandbox import staged_recipe_command
from build.bootstrap.cross_chroot_ownership import snapshot_imported_root,check_staged_install,merge_staged_install,OwnershipError
from build.bootstrap.cross_chroot import STAGE
with TemporaryDirectory(prefix='fs002-install-') as d:
    base=Path(d); work=base/'build'; root=base/'root'; stage=base/'stage'
    for x in (work,root,stage):x.mkdir()
    # recipe_command validates that both sandbox-visible /work paths exist.
    (work/'source').mkdir()
    (work/'build').mkdir()
    with patch('build.host_sandbox._bwrap',return_value='/usr/bin/bwrap'):
        cmd=staged_recipe_command(work,root,stage,STAGE/'recipes/bash.sh',source_dir='/work/source',build_dir='/work/build',package='bash',version='5.3',step_id='bash')
    assert '--unshare-net' in cmd and '--clearenv' in cmd
    assert ['--ro-bind',str(root),'/toolchain'] == cmd[cmd.index(str(root))-1:cmd.index(str(root))+2]
    assert ['--bind',str(stage),'/install'] == cmd[cmd.index(str(stage))-1:cmd.index(str(stage))+2]
    assert ['--setenv','DISTRO_ROOT_DIR','/install'] == cmd[cmd.index('DISTRO_ROOT_DIR')-1:cmd.index('DISTRO_ROOT_DIR')+2]
    assert cmd[-2:]==['/bin/bash','/recipe/selected.sh']
    (root/'existing').write_text('original'); before=snapshot_imported_root(root)
    (stage/'existing').write_text('different')
    try:check_staged_install(root,stage)
    except OwnershipError:pass
    else:raise AssertionError('collision accepted')
    assert snapshot_imported_root(root)==before
    (stage/'existing').unlink(); (stage/'new').write_text('new')
    merge_staged_install(root,stage)
    assert (root/'new').read_text()=='new' and (root/'existing').read_text()=='original'
''')


def native_verification_contract() -> bool:
    """NR-009,010: bounded GCC transitions and native/ELF gate construction."""
    return _check('''
import inspect
from build.bootstrap import cross_chroot_construction as c
from build.bootstrap import cross_chroot_elf_audit as elf
assert len(c.REVIEWED_GCC_DUPLICATES)==10
assert len(c.REVIEWED_GCC_PRIOR_RUNTIME)==7
candidate=inspect.getsource(c.construct_native_gcc_candidate_root)
assert 'shutil.copytree(installed, candidate, symlinks=True)' in candidate
assert 'merge_staged_install(candidate, stage)' in candidate
smoke=inspect.getsource(c.verify_native_gcc_candidate)
for fragment in ('--unshare-net','--ro-bind','/bin/bash','smoke.c','smoke.cpp',
 '/usr/bin/gcc','/usr/bin/g++','NATIVE_BASH_UTILITIES_C_CPP_OK','audit_native_elf'):
    assert fragment in smoke, fragment
assert {'/usr/bin/bash','/usr/bin/gcc','/usr/bin/g++','/verify/smoke-c','/verify/smoke-cpp'} <= set(elf.BINARIES)
reloc=inspect.getsource(c.verify_native_gcc_relocation)
assert 'TemporaryDirectory' in reloc and 'verify_native_gcc_candidate' in reloc
''')


def publication_failure_contract() -> bool:
    """NR-011,012: handoff marker rejection, exact identity and publish ordering."""
    return _check('''
import copy,io,tarfile,inspect
from pathlib import Path
from tempfile import TemporaryDirectory
from build.bootstrap.cross_chroot_handoff import ARCHIVE_NAME,validate_cross_chroot_handoff,validate_published_cross_chroot,publish_cross_chroot
from build.bootstrap.cross_toolchain_metadata import sha256_file
from build.selection import SelectionError
with TemporaryDirectory(prefix='fs002-publish-') as d:
    root=Path(d); archive=root/ARCHIVE_NAME
    with tarfile.open(archive,'w:xz',format=tarfile.PAX_FORMAT) as t:
        directory=tarfile.TarInfo('./usr');directory.type=tarfile.DIRTYPE;directory.mode=0o755;t.addfile(directory)
        payload=b'content'; entry=tarfile.TarInfo('./usr/example');entry.size=len(payload)
        t.addfile(entry,io.BytesIO(payload))
    m={'schema_version':1,'artifact':{'type':'cross-chroot','stage':'1B',
       'filename':ARCHIVE_NAME,'format':'tar.xz','sha256':sha256_file(archive),'size_bytes':archive.stat().st_size},
       'parent_stage_1a':{'filename':'cross-toolchain.tar.xz','sha256':'a'*64},
       'toolchain':{'target':'x86_64-distro-linux-gnu','runtime_root':'/'},
       'sources':[{'step':id,'package':pkg,'version':'2.47','sha256':'b'*64,
                   'recipe':id+'.sh','supplements':[]} for id,pkg in
                   [('native-binutils','binutils'),('native-gcc','gcc')]],
       'verification':{'functional':'passed','relocation':'passed','elf_dependencies':'passed','dependency_graph_sha256':'d'*64}}
    validate_cross_chroot_handoff(archive,m)
    def reject(m):
        try:validate_cross_chroot_handoff(archive,m)
        except (SelectionError,RuntimeError):return
        raise AssertionError('invalid handoff accepted')
    for section,key,value in [('artifact','sha256','0'*64),('artifact','size_bytes',0),
      ('verification','functional','failed'),('verification','relocation','failed'),
      ('verification','elf_dependencies','failed'),('parent_stage_1a','sha256','invalid')]:
        bad=copy.deepcopy(m);bad[section][key]=value;reject(bad)
    try:validate_published_cross_chroot(root)
    except (SelectionError,FileNotFoundError):pass
    else:raise AssertionError('archive without metadata accepted')
    source=inspect.getsource(publish_cross_chroot)
    assert source.index('temp_archive.replace(final_archive)')<source.index('temp_metadata.replace(final_metadata)')
    assert 'validate_published_cross_chroot(artifacts)' in source
    assert 'final_archive.unlink(missing_ok=True)' in source
''')


def traceability_contract() -> bool:
    """NR-014: each active mechanical FS-002 requirement has registered bindings."""
    from validate_product import TASKS
    spec = (ROOT/'product/specs/FS-002-cross-chroot.md').read_text()
    evaluation = json.loads((ROOT/'product/validation/requirement-evaluation.json').read_text())
    expected = {f'FS-002-NR-{n:03}' for n in list(range(1,13))+[14]}
    sections = re.split(r'(?=^### FS-002-NR-\d{3})',spec,flags=re.M)
    actual = set()
    for section in sections:
        found = re.match(r'### (FS-002-NR-\d{3})',section)
        if not found or found.group(1) not in expected:continue
        if '**State: Inactive**' in section:return False
        if not ('**Classification: B**' in section or '**Classification: M**' in section):return False
        actual.add(found.group(1))
    if actual != expected:return False
    bound = {item['requirement']:item['tasks'] for item in evaluation['bindings']}
    return all(r in bound and bound[r] and all(t in TASKS and t.startswith('fs002-') for t in bound[r]) for r in expected)
