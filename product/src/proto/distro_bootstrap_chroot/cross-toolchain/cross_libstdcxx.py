#!/usr/bin/env python3
"""Post-glibc target C++ runtime using the already-verified cross GCC source.

Runs in an isolated build sandbox and installs only new staged paths. GCC and
Binutils stamps are never altered. No host libstdc++ is imported into root.
"""
import argparse, hashlib, json, os, pathlib, subprocess, sys, tarfile, shutil
HERE=pathlib.Path(__file__).resolve().parent
TARGET='x86_64-distro-linux-gnu'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def run(argv,log,timeout=10800):
    with log.open('a') as f:
        f.write('STEP '+' '.join(argv)+'\n'); f.flush()
        p=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
    if p.returncode:raise RuntimeError(f'command failed ({p.returncode}), inspect {log}')

def sandbox(root,work):
    c=['bwrap','--die-with-parent','--new-session','--unshare-user','--unshare-pid','--unshare-net','--unshare-ipc','--unshare-uts','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/run','--ro-bind',str(root),'/toolchain','--bind',str(work),'/work','--chdir','/work/build','--clearenv','--setenv','HOME','/work','--setenv','LC_ALL','C','--setenv','PATH','/toolchain/usr/bin:/usr/bin:/bin']
    for d in ('usr','bin','sbin','lib','lib64','etc'):
        if (pathlib.Path('/')/d).exists():c+=['--ro-bind','/'+d,'/'+d]
    return c+['--']

def target_test(root,work):
    src=work/'probe.cc';src.write_text('#include <string>\n#include <cstdio>\nint main(){std::string s="distro-cxx-ok";std::puts(s.c_str());}\n')
    log=work/'cxx-validation.log'
    cc=f'/toolchain/usr/bin/{TARGET}-g++'
    command=sandbox(root,work)+[cc,'--sysroot=/toolchain','-fno-link-libatomic','-B/toolchain/usr/lib64/','-L/toolchain/usr/lib64','-Wl,-rpath-link,/toolchain/usr/'+TARGET+'/lib64','/work/probe.cc','-o','/work/probe']
    run(command,log,120)
    run(sandbox(root,work)+['/toolchain/lib64/ld-linux-x86-64.so.2','--library-path','/toolchain/usr/lib:/toolchain/usr/lib64:/toolchain/lib64:/toolchain/usr/'+TARGET+'/lib64','/work/probe'],log,120)
    output=subprocess.run(sandbox(root,work)+['/toolchain/lib64/ld-linux-x86-64.so.2','--library-path','/toolchain/usr/lib:/toolchain/usr/lib64:/toolchain/lib64:/toolchain/usr/'+TARGET+'/lib64','/work/probe'],capture_output=True,text=True,timeout=120)
    if output.returncode or output.stdout.strip()!='distro-cxx-ok':raise RuntimeError('C++ runtime acceptance test failed: '+output.stderr[-900:])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=pathlib.Path,required=True);ap.add_argument('--project',type=pathlib.Path,required=True);args=ap.parse_args()
    project=args.project.resolve();root=args.root.resolve()
    if os.geteuid()==0 or root!=project/'root' or root.is_symlink():raise RuntimeError('unsafe root/user')
    recipe_path=HERE/'recipes/cross-libstdcxx.json';recipe=json.loads(recipe_path.read_text())
    stamp=project/'.distro-bootstrap/stamps/cross-toolchain-libstdcxx.json';stamp.parent.mkdir(parents=True,exist_ok=True)
    signature=sha(recipe_path)
    if stamp.exists():
        rec=json.loads(stamp.read_text())
        if rec.get('signature')!=signature or rec.get('status')!='complete':raise RuntimeError('changed libstdc++ recipe on installed root; use clean root')
        for relative,proof in rec['installed'].items():
            p=root/relative
            if 'sha256' in proof and (not p.is_file() or sha(p)!=proof['sha256']):raise RuntimeError('modified stamped C++ file '+relative)
            if 'link' in proof and (not p.is_symlink() or os.readlink(p)!=proof['link']):raise RuntimeError('modified stamped C++ link '+relative)
        work=project/'.distro-bootstrap/validation/cross-libstdcxx';work.mkdir(parents=True,exist_ok=True)
        target_test(root,work);print('[cross-libstdcxx] SKIP verified stamp; C++ runtime PASS',flush=True);return
    # Locate GCC source archive from verified, successful cross GCC workspace. It
    # is not allowed to substitute an arbitrary system GCC source directory.
    gcc_stamp=project/'.distro-bootstrap/stamps/cross-toolchain/gcc.json'
    if not gcc_stamp.is_file():raise RuntimeError('missing verified GCC package stamp')
    gcc=json.loads(gcc_stamp.read_text())
    if gcc.get('status')!='complete' or not gcc.get('source_checksum'):raise RuntimeError('invalid GCC source provenance')
    candidate=[]
    for w in sorted((project/'.distro-bootstrap/work/cross-toolchain').glob('gcc-*')):
        a=w/'source.tar'
        if a.is_file() and hashlib.new(gcc.get('source_checksum_algorithm','sha512'),a.read_bytes()).hexdigest()==gcc['source_checksum']:candidate.append(a)
    if not candidate:raise RuntimeError('cannot locate pinned GCC source archive from existing cross GCC build')
    runroot=project/'.distro-bootstrap/work/cross-libstdcxx';runroot.mkdir(parents=True,exist_ok=True)
    n=1
    while (runroot/f'run-{n:03d}').exists():n+=1
    work=runroot/f'run-{n:03d}';(work/'build').mkdir(parents=True);(work/'stage').mkdir();(work/'src').mkdir()
    with tarfile.open(candidate[-1],'r:*') as t:t.extractall(work/'src',filter='data')
    src=next((work/'src').glob('gcc-*/configure'),None)
    (work/'src-tree').mkdir()
    if src is None:raise RuntimeError('GCC configure missing in verified source archive')
    # GCC configure expects /work/src/configure; expose extracted source tree read-only.
    root_src=src.parent;guest=sandbox(root,work)
    mount=guest[:-1]+['--ro-bind',str(root_src),'/work/src-tree','--']
    env={'target':TARGET,'jobs':str(min(os.cpu_count() or 2,8))}
    log=work/'build.log'
    for step in recipe['steps']:
        argv=[arg.format_map(env) for arg in step['argv']]
        if argv[0]=='/work/src/configure':argv[0]='/work/src-tree/configure'
        print('[cross-libstdcxx] step='+step['name'],flush=True)
        run(mount+argv,log)
    stage=work/'stage/toolchain/usr'
    if not stage.is_dir():raise RuntimeError('missing staged /toolchain/usr')
    # Some GCC install targets restage GCC-owned startup objects alongside
    # libstdc++. Never replace these files: validate their existing package
    # stamps and omit only previously owned, verified entries.
    prior_owned={}
    stamps_dir=project/'.distro-bootstrap/stamps/cross-toolchain'
    for package in ('binutils','gcc','linux-api-headers','glibc'):
        package_stamp=stamps_dir/(package+'.json')
        if not package_stamp.is_file():
            raise RuntimeError('missing completed cross package stamp: '+package)
        prior=json.loads(package_stamp.read_text())
        if prior.get('status')!='complete' or not prior.get('installed'):
            raise RuntimeError('invalid cross package stamp: '+package)
        for item in prior['installed']:
            rel=item['path']
            if rel in prior_owned:
                raise RuntimeError('duplicate stamped path: '+rel)
            dest=root/rel
            if 'sha256' in item:
                if not dest.is_file() or dest.is_symlink() or sha(dest)!=item['sha256']:
                    raise RuntimeError('changed cross package file: '+rel)
            elif 'link' in item:
                if not dest.is_symlink() or os.readlink(dest)!=item['link']:
                    raise RuntimeError('changed cross package symlink: '+rel)
            else:
                raise RuntimeError('invalid stamped entry: '+rel)
            prior_owned[rel]=package
    # An earlier attempt may have installed this package's files before
    # failing its C++ validation, leaving no completion stamp. Accept them
    # only if byte-for-byte equal to the staging output of a prior attempt
    # using this same recipe family; never treat arbitrary root contents as
    # recoverable package files.
    prior_stages=[]
    for older in sorted(runroot.glob('run-*')):
        if older==work or not older.is_dir():
            continue
        stage_previous=older/'stage/toolchain/usr'
        if stage_previous.is_dir():
            prior_stages.append(stage_previous)
    entries=[]
    reused=0
    recovered={}
    for p in sorted(stage.rglob('*')):
        rel=pathlib.Path('usr')/p.relative_to(stage);dst=root/rel
        if rel.as_posix()=='usr/share/info/dir':continue
        if p.is_symlink():
            link=os.readlink(p)
            if pathlib.Path(link).is_absolute():raise RuntimeError('absolute staged symlink '+str(rel))
            kind='link'
        elif p.is_dir():kind='dir'
        elif p.is_file():kind='file'
        else:raise RuntimeError('unsupported stage entry '+str(rel))
        if kind=='dir':
            if dst.is_symlink() or (dst.exists() and not dst.is_dir()):raise RuntimeError('directory collision '+str(rel))
        elif dst.exists() or dst.is_symlink():
            if rel.as_posix() in prior_owned:
                # Skip restaged files which belong to an already verified
                # cross-toolchain package. Never overwrite their stamp-owned
                # paths even if this build produced different bytes.
                reused+=1
                continue
            # Recovery is allowed only for the exact same path and bytes
            # previously staged by an interrupted libstdc++ build.
            earlier=[stage_old/p.relative_to(stage) for stage_old in prior_stages]
            if kind=='file' and dst.is_file() and not dst.is_symlink():
                digest=sha(dst)
                if any(q.is_file() and not q.is_symlink() and sha(q)==digest for q in earlier):
                    recovered[str(rel)]={'sha256':digest}
                    continue
            if kind=='link' and dst.is_symlink():
                link=os.readlink(dst)
                if any(q.is_symlink() and os.readlink(q)==link for q in earlier):
                    recovered[str(rel)]={'link':link}
                    continue
            raise RuntimeError('unowned file collision '+str(rel)+' (not a verified previous stage)')
        entries.append((p,dst,kind,rel))
    installed={};created=[]
    try:
        for src,dst,kind,rel in entries:
            if kind=='dir':
                if not dst.exists():dst.mkdir(parents=True);created.append(dst)
            else:
                dst.parent.mkdir(parents=True,exist_ok=True)
                if kind=='link':dst.symlink_to(os.readlink(src));installed[str(rel)]={'link':os.readlink(src)}
                else:shutil.copy2(src,dst);installed[str(rel)]={'sha256':sha(dst)}
                created.append(dst)
        target_test(root,work)
    except Exception:
        # Keep files intact after successful installation, allowing diagnosis;
        # refuse an unsafe blind retry on untracked files.
        raise
    installed.update(recovered)
    if not installed:raise RuntimeError('empty libstdc++ stage')
    print(f'[cross-libstdcxx] skipped {reused} verified prior-package files; recovered {len(recovered)} previous-stage files',flush=True)
    data={'schema_version':1,'status':'complete','signature':signature,'installed':installed}
    temp=stamp.with_suffix('.tmp');temp.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n');os.replace(temp,stamp)
    print('[cross-libstdcxx] COMPLETE; C++ compile/link/execute PASS',flush=True)

if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,ValueError,KeyError,subprocess.TimeoutExpired,tarfile.TarError) as e:
        print('[cross-libstdcxx] ERROR: '+str(e),file=sys.stderr,flush=True);sys.exit(1)
