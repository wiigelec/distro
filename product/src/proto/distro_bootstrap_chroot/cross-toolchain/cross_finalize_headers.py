#!/usr/bin/env python3
"""Finalize GCC's freestanding limits.h against the installed glibc headers.

GCC was built --without-headers; after glibc exists, merge GCC's
limitx.h + glimits.h + limity.h and validate target MB_LEN_MAX.
The owned-file stamp is updated atomically for intentional finalization.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

TARGET = 'x86_64-distro-linux-gnu'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def check(command):
    p = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
    if p.returncode:
        raise RuntimeError('command failed: ' + ' '.join(command) + '\n' + p.stderr[-2000:])
    return p.stdout

def atomic_json(path, obj):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')
    os.replace(temp, path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True, type=Path)
    ap.add_argument('--project', required=True, type=Path)
    args = ap.parse_args()
    project = args.project.resolve()
    root = args.root.resolve()
    if root != project / 'root' or not root.is_dir():
        raise RuntimeError('unexpected toolchain root')
    stamp_path = project / '.distro-bootstrap/stamps/cross-toolchain/gcc.json'
    glibc_stamp = project / '.distro-bootstrap/stamps/cross-toolchain/glibc.json'
    if not glibc_stamp.is_file() or json.loads(glibc_stamp.read_text()).get('status') != 'complete':
        raise RuntimeError('glibc must be installed before GCC header finalization')
    stamp = json.loads(stamp_path.read_text())
    if stamp.get('status') != 'complete':
        raise RuntimeError('GCC completion stamp absent')
    version = stamp['resolved_version']
    if not version.replace('.', '').isdigit():
        raise RuntimeError('invalid GCC source version')
    result = Path(stamp['result']).resolve()
    workspace = result.with_name(result.name.removesuffix('-result.json'))
    source = workspace / 'src' / ('gcc-' + version) / 'gcc'
    if not source.is_dir() or not source.resolve().is_relative_to(project / '.distro-bootstrap/work/cross-toolchain'):
        raise RuntimeError('GCC source workspace missing or unsafe')
    assembled = b''.join((source / name).read_bytes() for name in ('limitx.h','glimits.h','limity.h'))
    if b'#include_next' not in assembled:
        raise RuntimeError('GCC target-aware limits header lacks include_next')
    installed = root / 'usr/lib/gcc' / TARGET / version / 'include/limits.h'
    relative = installed.relative_to(root).as_posix()
    entries = [e for e in stamp.get('installed', []) if e.get('path') == relative]
    if len(entries) != 1 or 'sha256' not in entries[0] or not installed.is_file() or installed.is_symlink():
        raise RuntimeError('installed GCC limits.h not in package ownership stamp')
    observed = sha(installed)
    if observed != entries[0]['sha256']:
        raise RuntimeError('installed GCC limits.h fails ownership checksum')
    if installed.read_bytes() != assembled:
        temp = installed.with_name('limits.h.distro-finalize-tmp')
        if temp.exists() or temp.is_symlink():
            raise RuntimeError('stale limits.h temporary file')
        temp.write_bytes(assembled)
        temp.chmod(installed.stat().st_mode & 0o777)
        os.replace(temp, installed)
        entries[0]['sha256'] = sha(installed)
        atomic_json(stamp_path, stamp)
        print('[finalize] GCC limits.h reconstructed from limitx/glimits/limity', flush=True)
    else:
        print('[finalize] GCC limits.h: SKIP verified finalized header', flush=True)
    work = project / '.distro-bootstrap/validation/cross-toolchain-headers'
    work.mkdir(parents=True, exist_ok=True)
    test = work / 'limits.c'
    test.write_text('#include <limits.h>\n#include <wchar.h>\n#if MB_LEN_MAX != 16\n#error bad MB_LEN_MAX\n#endif\nint distro_limits_probe(void) { return MB_LEN_MAX; }\n')
    command = ['bwrap', '--die-with-parent','--new-session','--unshare-user','--unshare-pid',
               '--unshare-net','--unshare-ipc','--unshare-uts','--proc','/proc','--dev','/dev',
               '--tmpfs','/tmp','--dir','/run','--ro-bind',str(root),'/toolchain',
               '--bind',str(work),'/work','--clearenv','--setenv','PATH','/toolchain/bin:/usr/bin:/bin',
               '--setenv','LC_ALL','C']
    for name in ('usr','bin','sbin','lib','lib64','etc'):
        if (Path('/') / name).exists():
            command += ['--ro-bind','/' + name,'/' + name]
    command += ['--','/toolchain/bin/' + TARGET + '-gcc','--sysroot=/toolchain',
                '-O2','-D_FORTIFY_SOURCE=2','-c','/work/limits.c','-o','/work/limits.o']
    check(command)
    if not (work / 'limits.o').is_file():
        raise RuntimeError('target limits.h compile did not produce object')
    print('[finalize] MB_LEN_MAX=16 and fortified wchar.h compile: PASS', flush=True)

if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as e:
        print('[finalize] ERROR: ' + str(e), file=sys.stderr, flush=True)
        sys.exit(1)
