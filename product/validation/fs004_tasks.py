"""FS-004 initial Build slice validation; no requirements activated yet."""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import os, subprocess, sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "product/src"


def native_selection_contract() -> bool:
    script = r'''
from pathlib import Path
from tempfile import TemporaryDirectory
from build.selection import load_manifests, SelectionError
from build.native_selection import resolve_native_dependencies
from build.bootstrap.cross_toolchain import PACKAGES
legacy = load_manifests(PACKAGES)
assert legacy['sed'].source.kind == 'upstream'
assert legacy['sed'].dependencies == ()
assert legacy['glibc'].dependencies == ('gcc','linux')
assert not legacy['glibc'].build_link_dependencies
with TemporaryDirectory() as d:
    root = Path(d)
    def write(name, source='upstream', **deps):
        import yaml
        s = {'name':name, 'source': {'url':'https://example.org/'+name+'-{version}.tar.xz','verification':'sha256'} if source=='upstream' else {'kind':'local','paths':['product/definitions/'+name+'.txt']}}
        s.update(deps)
        (root/(name+'.yaml')).write_text(yaml.safe_dump(s))
    write('filesystem', source='local')
    write('bash',build_tools=['filesystem'],runtime_dependencies=['filesystem'])
    write('sed',build_tools=['bash'],runtime_dependencies=['bash','filesystem'])
    m=load_manifests(root)
    assert m['filesystem'].source.kind == 'local'
    assert m['filesystem'].source.paths == ('product/definitions/filesystem.txt',)
    plan=resolve_native_dependencies({'filesystem':'1','bash':'5.3','sed':'4.10'},m)
    assert plan.construction_order == ('filesystem','bash','sed')
    assert plan.installed_order == ('filesystem','bash','sed')
    assert plan.installed_relationships['sed']==(('bash','5.3'),('filesystem','1'))
    imported=resolve_native_dependencies({'filesystem':'1','bash':'5.3','sed':'4.10'},m, imported={'bash':'5.3'})
    assert imported.construction_order == ('filesystem','bash','sed') or imported.construction_order == ('filesystem','sed','bash')
    assert imported.installed_relationships==plan.installed_relationships
    for selected in ({'filesystem':'1','sed':'4.10'}, {'sed':'4.10'}):
        try:resolve_native_dependencies(selected,m)
        except SelectionError:pass
        else:raise AssertionError('missing dependency accepted')
    write('sed', build_tools=['bash'],runtime_dependencies=['bash','filesystem'], dependencies=['bash'])
    try:load_manifests(root)
    except SelectionError:pass
    else:raise AssertionError('mixed legacy and categorized dependencies accepted')
    write('sed',build_tools=['bash'],runtime_dependencies=['bash','filesystem'])
    write('bash',build_tools=['sed'],runtime_dependencies=['filesystem'])
    m=load_manifests(root)
    try:resolve_native_dependencies({'filesystem':'1','bash':'5.3','sed':'4.10'},m)
    except SelectionError as e:assert 'cyclic' in str(e)
    else:raise AssertionError('construction cycle accepted')
    write('bash',build_tools=['filesystem'],runtime_dependencies=['sed'])
    m=load_manifests(root)
    try:resolve_native_dependencies({'filesystem':'1','bash':'5.3','sed':'4.10'},m)
    except SelectionError as e:assert 'cyclic' in str(e)
    else:raise AssertionError('installation cycle accepted')
    write('bash',build_tools=['filesystem'],runtime_dependencies=['filesystem'])
    m=load_manifests(root)
    try:resolve_native_dependencies({'filesystem':'1','bash':'5.3','sed':'4.10'},m,imported={'bash':'0.1'})
    except SelectionError:pass
    else:raise AssertionError('imported version conflict accepted')
    (root/'filesystem.yaml').write_text('name: filesystem\nsource:\n  kind: local\n  paths: [../outside]\n')
    try:load_manifests(root)
    except SelectionError:pass
    else:raise AssertionError('unsafe local source path accepted')
'''
    env = {'PATH': os.defpath, 'PYTHONPATH': str(SRC), 'PYTHONDONTWRITEBYTECODE':'1'}
    r = subprocess.run([sys.executable, '-B', '-c', script], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stderr or r.stdout, file=sys.stderr)
    return r.returncode == 0
