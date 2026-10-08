#!/usr/bin/env python3
"""Manifest-driven cross-toolchain prototype; no package-specific recipe hardcoding."""
import argparse, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tarfile, urllib.request
ROOT=pathlib.Path(__file__).resolve().parent

def load(path): return json.loads(path.read_text())
def finish(report,out):
    payload=json.dumps(report,indent=2,sort_keys=True)+"\n"
    if out: out.parent.mkdir(parents=True,exist_ok=True);out.write_text(payload)
    else: print(payload,end="")
    return 0 if report['status']=='provisional-pass' else 1

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);ap.add_argument('--workspace',type=pathlib.Path,required=True);ap.add_argument('--out',type=pathlib.Path);args=ap.parse_args()
    m=load(ROOT/'cross-toolchain-manifest.json'); matches=[p for p in m['packages'] if p['name']==args.package]
    report={'schema_version':1,'phase':'cross-toolchain','package':args.package,'status':'blocked'}
    if len(matches)!=1:report['reason']='package absent or duplicated';return finish(report,args.out)
    p=matches[0]
    if p.get('state') != 'executable' or not p.get('source') or not p.get('recipe') or not p.get('host_version'):
        report['reason']='host version mapping/source or recipe unresolved for this package';return finish(report,args.out)
    probe=p['host_version']
    try:
        observed=subprocess.run(probe['argv'],capture_output=True,text=True,timeout=20,check=False,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        if observed.returncode:raise ValueError('host version probe failed')
        banner=observed.stdout.strip()
        found=re.search(probe['regex'],banner)
        if not found:raise ValueError('unsupported host version output: '+banner[:180])
        version=found.group(1)
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,2}',version):raise ValueError('unsafe source version')
        report['host_version_banner']=banner.splitlines()[0]
        report['resolved_version']=version
        source=p['source']
        filename=source['archive_template'].format(version=version)
        url=source['url_template'].format(version=version)
        with urllib.request.urlopen(source['sha512_index'],timeout=45) as checksum_stream:
            checksum_text=checksum_stream.read(2_000_000).decode('utf-8')
        matches=[]
        for line in checksum_text.splitlines():
            bits=line.split()
            if len(bits)==2 and bits[1].lstrip('*').removeprefix('./')==filename and re.fullmatch('[a-fA-F0-9]{128}',bits[0]):
                matches.append(bits[0].lower())
        if len(matches)!=1:raise ValueError('exact archive checksum entry missing or ambiguous')
        expected_digest=matches[0]
        report['source']={'url':url,'archive':filename,'sha512_index':source['sha512_index'],'expected_sha512':expected_digest,'checksum_authentication':'HTTPS transport only; no signature verification'}
    except Exception as e:
        report['reason']='host discovery/source resolution failed: '+str(e)[:260];return finish(report,args.out)
    if os.geteuid()==0 or not shutil.which('bwrap'):
        report['reason']='requires non-root user and bubblewrap';return finish(report,args.out)
    base=args.workspace.resolve()
    if base.exists() and any(base.iterdir()):report['reason']='workspace must be empty';return finish(report,args.out)
    recipe_path=(ROOT/p['recipe']).resolve()
    if not recipe_path.is_relative_to(ROOT) or not recipe_path.is_file():report['reason']='invalid recipe reference';return finish(report,args.out)
    r=load(recipe_path)
    if r['name']!=p['name'] or r['phase']!=m['phase']:report['reason']='recipe identity mismatch';return finish(report,args.out)
    if not isinstance(r.get('steps'),list) or not r['steps']:report['reason']='missing recipe steps';return finish(report,args.out)
    base.mkdir(parents=True,exist_ok=True);(base/'logs').mkdir();(base/'build').mkdir();(base/'prefix').mkdir()
    archive=base/'source.tar';h=hashlib.sha512()
    try:
        with urllib.request.urlopen(url,timeout=90) as src, archive.open('wb') as f:
            while True:
                part=src.read(1024*1024)
                if not part:break
                h.update(part);f.write(part)
        report['source_sha512']=h.hexdigest()
        if h.hexdigest()!=expected_digest:report['reason']='source checksum mismatch';return finish(report,args.out)
        with tarfile.open(archive,'r:*') as f:f.extractall(base/'src',filter='data')
    except Exception as e:report['reason']='fetch/extract failed: '+str(e)[:300];return finish(report,args.out)
    vars={'version':version,'target':m['target']}
    try:
        (base/'check.s').write_text(r['validation']['assembly_source'])
        steps=[]
        for s in r['steps']:
            argv=[v.format_map(vars) for v in s['argv']]
            if not argv or any(not isinstance(v,str) or not v for v in argv):raise ValueError('invalid argv')
            steps.append({'name':s['name'],'argv':argv})
        # Only explicit steps from the reviewed recipe; no arbitrary shell evaluation.
        guest="""import json,subprocess,sys
steps=json.load(open("/work/steps.json"))
with open("/work/logs/build.log","w") as log:
 for step in steps:
  log.write("STEP "+step["name"]+"\\n");log.flush()
  p=subprocess.run(step["argv"],cwd="/work/build",stdout=log,stderr=subprocess.STDOUT,check=False)
  if p.returncode:sys.exit(p.returncode)
"""
        (base/'steps.json').write_text(json.dumps(steps));(base/'guest.py').write_text(guest)
        cmd=[shutil.which('bwrap'),'--die-with-parent','--new-session','--unshare-user','--unshare-pid','--unshare-net','--unshare-ipc','--unshare-uts','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/run','--bind',str(base),'/work','--chdir','/work/build','--clearenv','--setenv','HOME','/work','--setenv','PATH','/work/prefix/bin:/usr/bin:/bin','--setenv','LC_ALL','C']
        for name in ('usr','bin','sbin','lib','lib64','etc'):
            if (pathlib.Path('/')/name).exists():cmd += ['--ro-bind','/'+name,'/'+name]
        cmd += ['--','/usr/bin/python3','/work/guest.py']
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=7200,check=False)
        report['build_exit_code']=result.returncode;report['stderr']=result.stderr[-2000:]
        if result.returncode:report['reason']='recipe step failed; see workspace logs';return finish(report,args.out)
        outputs=[pathlib.Path(x.format_map(vars)) for x in r['validation']['tools']]
        # Sandbox /work maps to base on host.
        report['tool_paths_exist']=all((base/path.relative_to('/work')).is_file() for path in outputs)
        report['relocatable_object_exists']=(base/'check-reloc.o').is_file()
        if not (report['tool_paths_exist'] and report['relocatable_object_exists']):report['reason']='expected recipe outputs missing';return finish(report,args.out)
        report['status']='provisional-pass';report['limitations']=['runtime and target sysroot closure unproven','source checksum is not a signature']
    except Exception as e:report['reason']='execution failed: '+str(e)[:300]
    return finish(report,args.out)
if __name__=='__main__':raise SystemExit(main())
