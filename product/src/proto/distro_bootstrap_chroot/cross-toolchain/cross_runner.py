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
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);ap.add_argument('--workspace',type=pathlib.Path,required=True);ap.add_argument('--toolchain-root',type=pathlib.Path);ap.add_argument('--out',type=pathlib.Path);args=ap.parse_args()
    m=load(ROOT/'cross-toolchain-manifest.json'); matches=[p for p in m['packages'] if p['name']==args.package]
    report={'schema_version':1,'phase':'cross-toolchain','package':args.package,'status':'blocked'}
    if len(matches)!=1:report['reason']='package absent or duplicated';return finish(report,args.out)
    p=matches[0]
    source_owner=p
    if p.get('source_package'):
        owners=[x for x in m['packages'] if x['name']==p['source_package']]
        if len(owners)!=1 or owners[0] is p or not owners[0].get('source'):
            report['reason']='invalid source_package dependency';return finish(report,args.out)
        source_owner=owners[0]
    if p.get('state') != 'executable' or not source_owner.get('source') or not p.get('recipe') or not source_owner.get('host_version'):
        report['reason']='host version mapping/source or recipe unresolved for this package';return finish(report,args.out)
    probe=source_owner['host_version']
    try:
        observed=subprocess.run(probe['argv'],capture_output=True,text=True,timeout=20,check=False,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        if observed.returncode:raise ValueError('host version probe failed')
        banner=observed.stdout.strip()
        found=re.search(probe['regex'],banner)
        if not found:raise ValueError('unsupported host version output: '+banner[:180])
        version=found.group(1)
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,2}',version):raise ValueError('unsafe source version')
        report['host_version_banner']=banner.splitlines()[0]
        report['host_version']=version
        policy=source_owner.get('upstream_version_policy','exact')
        if policy=='major-minor-zero-release': version='.'.join(version.split('.')[:2])+'.0'
        elif policy!='exact':raise ValueError('unsupported upstream version policy')
        report['resolved_version']=version
        source=source_owner['source']
        source_vars={'version':version,'major':version.split('.')[0]}
        filename=source['archive_template'].format_map(source_vars)
        url=source['url_template'].format_map(source_vars)
        signed_source='signature_url_template' in source
        checksum_algorithm='sha256' if 'sha256_index' in source or signed_source else 'sha512'
        if signed_source:
            signature_url=source['signature_url_template'].format_map(source_vars)
            report['source']={'url':url,'archive':filename,'signature_url':signature_url,'signature_authentication':'OpenPGP signature verified against manifest-approved signing subkey; signer identity requires independent review'}
        else:
            checksum_url=source[checksum_algorithm+'_index'].format_map(source_vars)
            with urllib.request.urlopen(checksum_url,timeout=45) as checksum_stream:
                checksum_text=checksum_stream.read(2_000_000).decode('utf-8')
            matches=[]
            for line in checksum_text.splitlines():
                bits=line.split()
                if len(bits)==2 and bits[1].lstrip('*').removeprefix('./')==filename and re.fullmatch('[a-fA-F0-9]{'+str(64 if checksum_algorithm=='sha256' else 128)+'}',bits[0]):
                    matches.append(bits[0].lower())
            if len(matches)!=1:raise ValueError('exact archive checksum entry missing or ambiguous')
            expected_digest=matches[0]
            report['source']={'url':url,'archive':filename,'checksum_index':checksum_url,'checksum_algorithm':checksum_algorithm,'expected_checksum':expected_digest,'checksum_authentication':'HTTPS transport only; signed index signature not verified'}
    except Exception as e:
        report['reason']='host discovery/source resolution failed: '+str(e)[:260];return finish(report,args.out)
    if os.geteuid()==0 or not shutil.which('bwrap'):
        report['reason']='requires non-root user and bubblewrap';return finish(report,args.out)
    toolchain_root=None
    if p.get('requires_toolchain_root'):
        if not args.toolchain_root:report['reason']='requires --toolchain-root';return finish(report,args.out)
        toolchain_root=args.toolchain_root.resolve()
        if not (toolchain_root/'bin'/ (m['target']+'-as')).is_file() or not (toolchain_root/'bin'/(m['target']+'-ld')).is_file():
            report['reason']='cross Binutils not found in toolchain root';return finish(report,args.out)
    base=args.workspace.resolve()
    if base.exists() and any(base.iterdir()):report['reason']='workspace must be empty';return finish(report,args.out)
    recipe_path=(ROOT/p['recipe']).resolve()
    if not recipe_path.is_relative_to(ROOT) or not recipe_path.is_file():report['reason']='invalid recipe reference';return finish(report,args.out)
    r=load(recipe_path)
    if r['name']!=p['name'] or r['phase']!=m['phase']:report['reason']='recipe identity mismatch';return finish(report,args.out)
    if not isinstance(r.get('steps'),list) or not r['steps']:report['reason']='missing recipe steps';return finish(report,args.out)
    base.mkdir(parents=True,exist_ok=True);(base/'logs').mkdir();(base/'build').mkdir();(base/'prefix').mkdir()
    archive=base/'source.tar';h=hashlib.new(checksum_algorithm)
    try:
        if p.get('source_package'):
            if toolchain_root is None:raise ValueError('source reuse requires toolchain root')
            project=toolchain_root.parent
            stamp_path=project/'.distro-bootstrap/stamps/cross-toolchain'/(p['source_package']+'.json')
            owner_stamp=load(stamp_path)
            if owner_stamp.get('status')!='complete' or owner_stamp.get('resolved_version')!=version:
                raise ValueError('verified source owner stamp missing or version mismatch')
            prior_result=pathlib.Path(owner_stamp['result']).resolve()
            workroot=(project/'.distro-bootstrap/work/cross-toolchain').resolve()
            if not prior_result.is_relative_to(workroot):raise ValueError('source owner result escapes work directory')
            prior_archive=prior_result.with_name(prior_result.name.removesuffix('-result.json'))/'source.tar'
            if not prior_archive.is_file():raise ValueError('verified source owner archive missing')
            owner_algorithm=owner_stamp['source_checksum_algorithm']
            if owner_algorithm!=checksum_algorithm:raise ValueError('source checksum algorithm mismatch')
            if hashlib.new(checksum_algorithm,prior_archive.read_bytes()).hexdigest()!=owner_stamp['source_checksum']:
                raise ValueError('verified source archive hash mismatch')
            shutil.copyfile(prior_archive,archive)
            h.update(archive.read_bytes())
        else:
            with urllib.request.urlopen(url,timeout=90) as src, archive.open('wb') as f:
                while True:
                    part=src.read(1024*1024)
                    if not part:break
                    h.update(part);f.write(part)
        report['source_checksum']=h.hexdigest()
        report['source_checksum_algorithm']=checksum_algorithm
        if signed_source:
            signature=base/'source.tar.sig'
            with urllib.request.urlopen(signature_url,timeout=90) as source_sig,signature.open('wb') as sig_file:
                sig_file.write(source_sig.read(20000))
            if not shutil.which('gpg'):
                report['reason']='signed glibc source requires gpg with an independently trusted release signing key';return finish(report,args.out)
            verify=subprocess.run(['gpg','--batch','--status-fd','1','--verify',str(signature),str(archive)],capture_output=True,text=True,timeout=90,check=False)
            status_lines=verify.stdout.splitlines()
            valid=[line.split() for line in status_lines if line.startswith('[GNUPG:] VALIDSIG ')]
            good=[line for line in status_lines if line.startswith('[GNUPG:] GOODSIG ')]
            invalid_markers=('BADSIG','ERRSIG','REVKEYSIG','EXPKEYSIG','SIGEXPIRED')
            invalid=[line for line in status_lines if any(line.startswith('[GNUPG:] '+flag+' ') for flag in invalid_markers)]
            approved=source.get('allowed_signer_fingerprints',[])
            if (not isinstance(approved,list) or not approved or
                any(not isinstance(fp,str) or not re.fullmatch('[A-F0-9]{40}',fp) for fp in approved)):
                report['reason']='missing or invalid manifest signing subkey allowlist'
                return finish(report,args.out)
            signer=valid[0][2].upper() if len(valid)==1 and len(valid[0])>2 else None
            if verify.returncode or len(valid)!=1 or len(good)!=1 or invalid or signer not in approved:
                report['reason']='glibc detached signature failed cryptographic validation or signer not approved in manifest'
                report['signature_diagnostics']=verify.stderr[-700:]
                report['observed_signer_fingerprint']=signer
                return finish(report,args.out)
            report['source']['signer_fingerprint']=signer
            report['source']['signature_verified']=True
            report['source']['signature_policy']='manifest-approved signing subkey (GPG ownertrust not consulted)'
        elif h.hexdigest()!=expected_digest:
            report['reason']='source checksum mismatch';return finish(report,args.out)
        with tarfile.open(archive,'r:*') as f:f.extractall(base/'src',filter='data')
    except Exception as e:report['reason']='fetch/extract failed: '+str(e)[:300];return finish(report,args.out)
    jobs_probe=subprocess.run(['nproc'],capture_output=True,text=True,timeout=20,check=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    jobs=int(jobs_probe.stdout.strip())
    if jobs<1 or jobs>4096:raise ValueError('invalid nproc result')
    report['build_jobs']=jobs
    vars={'version':version,'target':m['target'],'jobs':str(jobs)}
    try:
        fixtures=r['validation'].get('write_files',{})
        if 'assembly_source' in r['validation']:fixtures['check.s']=r['validation']['assembly_source']
        for name,body in fixtures.items():
            if pathlib.PurePath(name).name!=name or '/' in name or name in ('.','..'):raise ValueError('unsafe validation fixture')
            (base/name).write_text(body)
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
        cmd=[shutil.which('bwrap'),'--die-with-parent','--new-session','--unshare-user','--unshare-pid','--unshare-net','--unshare-ipc','--unshare-uts','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/run','--bind',str(base),'/work','--chdir','/work/build','--clearenv','--setenv','HOME','/work','--setenv','PATH','/toolchain/bin:/work/prefix/bin:/usr/bin:/bin','--setenv','LC_ALL','C']
        if toolchain_root:cmd+=['--ro-bind',str(toolchain_root),'/toolchain']
        for name in ('usr','bin','sbin','lib','lib64','etc'):
            if (pathlib.Path('/')/name).exists():cmd += ['--ro-bind','/'+name,'/'+name]
        cmd += ['--','/usr/bin/python3','/work/guest.py']
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=7200,check=False)
        report['build_exit_code']=result.returncode;report['stderr']=result.stderr[-2000:]
        if result.returncode:report['reason']='recipe step failed; see workspace logs';return finish(report,args.out)
        outputs=[pathlib.Path(x.format_map(vars)) for x in r['validation']['tools']]
        # Sandbox /work maps to base on host.
        report['tool_paths_exist']=all((base/path.relative_to('/work')).is_file() for path in outputs)
        for pattern in r['validation'].get('glob_tools',[]):
            pattern=pattern.format_map(vars)
            rel=pathlib.PurePosixPath(pattern)
            if not str(rel).startswith('/work/') or '..' in rel.parts:
                raise ValueError('unsafe validation glob')
            if not any(path.is_file() for path in base.glob(str(rel).removeprefix('/work/'))):
                report['tool_paths_exist']=False
        object_spec=r['validation'].get('relocatable_output','/work/check-reloc.o')
        report['relocatable_object_exists']=True if object_spec is None else (base/pathlib.Path(object_spec).relative_to('/work')).is_file()
        if not (report['tool_paths_exist'] and report['relocatable_object_exists']):report['reason']='expected recipe outputs missing';return finish(report,args.out)
        report['status']='provisional-pass';report['limitations']=['runtime and target sysroot closure unproven','source checksum is not a signature']
    except Exception as e:report['reason']='execution failed: '+str(e)[:300]
    return finish(report,args.out)
if __name__=='__main__':raise SystemExit(main())
