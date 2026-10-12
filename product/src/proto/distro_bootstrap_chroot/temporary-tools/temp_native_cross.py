#!/usr/bin/env python3
"""Build target-executable toolchain components with the host-executable Distro cross-GCC.

The source/archive, staging and collision checks are shared with temp_cross_package.
These packages are *cross-built on the host*, then executed/validated inside root.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

import temp_cross_package as common

HERE = Path(__file__).resolve().parent


def guest_run(root, work, argv, logfile, timeout=7200):
    common.run(common.sandbox(root, work, work / 'src-tree') + argv, logfile, timeout=timeout)


def validate_in_root(root, work, binary):
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-user',
           '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts',
           '--bind', str(root), '/', '--bind', str(work), '/work',
           '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
           '--clearenv', '--setenv', 'HOME', '/work',
           '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'LC_ALL', 'C', '--']
    p = subprocess.run(cmd + [binary, '--version'], capture_output=True, text=True, timeout=120)
    if p.returncode:
        raise RuntimeError('target executable test failed: ' + binary + '\n' + p.stderr[-1200:])


def compiler_smoke(root, work):
    source = work / 'probe.c'
    source.write_text('#include <stdio.h>\nint main(void){ puts("distro-native-gcc-ok");return 0;}\n')
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-user',
           '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts',
           '--bind', str(root), '/', '--bind', str(work), '/work',
           '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
           '--clearenv', '--setenv', 'HOME', '/work',
           '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'LC_ALL', 'C', '--']
    common.run(cmd + ['/usr/bin/gcc', '/work/probe.c', '-o', '/work/probe'], work / 'native-smoke.log', timeout=240)
    test = subprocess.run(cmd + ['/work/probe'], capture_output=True, text=True, timeout=90)
    if test.returncode or test.stdout.strip() != 'distro-native-gcc-ok':
        raise RuntimeError('native GCC compiled program failed in isolated chroot: ' + test.stderr[-1000:])
    print('[temp-tools] native-gcc: in-chroot compile/link/execute PASS', flush=True)


def recover_native_binutils(root, state, name, recipe, signature, source_hash, stamp):
    """Complete a prior install whose validation failed after the files were copied.

    Only accept a complete, byte-identical staged native Binutils payload. Never
    overwrite a file or declare success from the mere presence of as/ld.
    """
    if name != 'native-binutils' or stamp.exists():
        return False
    runs = state / 'work' / name
    if not runs.is_dir():
        return False
    for work in sorted(runs.glob('run-*'), reverse=True):
        stage = work / 'stage/usr'
        log = work / 'build.log'
        if not stage.is_dir() or not log.is_file():
            continue
        recorded = log.read_text(errors='replace')
        if recorded.count('STEP ') < len(recipe['steps']):
            continue
        proof = {}
        all_match = True
        for src in sorted(stage.rglob('*')):
            relative = src.relative_to(work / 'stage')
            if relative.as_posix() == 'usr/share/info/dir':
                continue
            dest = root / relative
            if src.is_symlink():
                target = os.readlink(src)
                if not dest.is_symlink() or os.readlink(dest) != target:
                    all_match = False
                    break
                proof[relative.as_posix()] = {'link': target}
            elif src.is_dir():
                if dest.is_symlink() or not dest.is_dir():
                    all_match = False
                    break
            elif src.is_file():
                if dest.is_symlink() or not dest.is_file() or common.sha(src) != common.sha(dest):
                    all_match = False
                    break
                proof[relative.as_posix()] = {'sha256': common.sha(dest)}
            else:
                all_match = False
                break
        if not all_match or not proof:
            continue
        for binary in recipe['validation']['chroot_executables']:
            if not (root / binary.lstrip('/')).is_file():
                raise RuntimeError('recovery missing native-binutils executable: ' + binary)
            validate_in_root(root, work, binary)
        common.save(stamp, {'schema_version':1, 'phase':'temp-tools',
                            'package':name, 'status':'complete',
                            'manifest_sha256':signature,
                            'source_sha256':source_hash, 'installed':proof})
        print(f'[temp-tools] {name}: RECOVERED prior install; {len(proof)} files/links verified', flush=True)
        return True
    return False


def main(project_arg, name):
    if os.geteuid() == 0:
        raise RuntimeError('run as regular user')
    project = Path(project_arg).expanduser().resolve()
    root, state = project / 'root', project / '.distro-bootstrap'
    if root.is_symlink() or state.is_symlink() or not root.is_dir() or not state.is_dir():
        raise RuntimeError('invalid target root/state')
    if not (state / 'temp-tools-import.json').is_file():
        raise RuntimeError('missing import marker')
    manifest = json.loads((HERE / 'temporary-tools-manifest.json').read_text())
    if manifest['phase'] != 'temp-tools' or manifest['target'] != 'x86_64-distro-linux-gnu':
        raise RuntimeError('manifest mismatch')
    candidates = [p for p in manifest['packages'] if p['name'] == name]
    if len(candidates) != 1:
        raise RuntimeError('missing package: ' + name)
    pkg = candidates[0]
    recipe_path = (HERE / pkg['recipe']).resolve()
    if not recipe_path.is_relative_to(HERE) or not recipe_path.is_file():
        raise RuntimeError('unsafe recipe path')
    recipe = json.loads(recipe_path.read_text())
    if recipe['name'] != name or recipe['execution'] != 'host-cross' or recipe['phase'] != 'temp-tools':
        raise RuntimeError('recipe identity mismatch')
    stamp = state / 'stamps' / (name + '.json')
    signature = hashlib.sha256((common.sha(recipe_path) + ':' + json.dumps(pkg, sort_keys=True)).encode()).hexdigest()
    if stamp.exists():
        record = json.loads(stamp.read_text())
        if record.get('status') != 'complete' or record.get('manifest_sha256') != signature or not record.get('installed'):
            raise RuntimeError('inconsistent package stamp: ' + name)
        for path, evidence in record['installed'].items():
            dest = root / path
            if 'sha256' in evidence and (not dest.is_file() or common.sha(dest) != evidence['sha256']):
                raise RuntimeError('stamped file modified: ' + path)
            if 'link' in evidence and (not dest.is_symlink() or os.readlink(dest) != evidence['link']):
                raise RuntimeError('stamped symlink modified: ' + path)
        if name == 'native-gcc':
            check_work = state / 'validation/native-gcc'
            check_work.mkdir(parents=True, exist_ok=True)
            compiler_smoke(root, check_work)
        print(f'[temp-tools] {name}: SKIP verified stamp', flush=True)
        return
    # The previous version performed installation before isolated validation.
    # Recover its byte-identical installed payload before refusing untracked binaries.
    if name == 'native-binutils':
        cached = state / 'sources' / (pkg['upstream_name'] + '-' + pkg['version'] + '.tar.xz')
        if cached.is_file() and common.sha(cached) == pkg['source']['sha256']:
            if recover_native_binutils(root, state, name, recipe, signature,
                                       common.sha(cached), stamp):
                return
    for binary in recipe['validation']['chroot_executables']:
        candidate = root / binary.lstrip('/')
        if candidate.exists() or candidate.is_symlink():
            raise RuntimeError('untracked package binary: ' + binary)
    source = pkg['source']
    version = pkg['version']
    if not re.fullmatch(r'[a-f0-9]{64}', source['sha256']):
        raise RuntimeError('unpinned source checksum')
    archive_name = source['url'].rsplit('/', 1)[1]
    if archive_name != pkg['upstream_name'] + '-' + version + '.tar.xz' and archive_name != pkg['upstream_name'] + '-' + version + '.tar.gz':
        raise RuntimeError('unexpected source filename')
    if not source['url'].startswith(('https://ftp.gnu.org/gnu/', 'https://gcc.gnu.org/pub/gcc/releases/')):
        raise RuntimeError('unapproved source origin')
    cache = state / 'sources'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / archive_name
    print(f'[temp-tools] {name}: downloading/verifying source', flush=True)
    common.obtain(source['url'], archive, source['sha256'])
    # Reuse the extracted tree only after validating that configure exists.
    tree = cache / ('extracted-' + archive_name.rsplit('.tar.', 1)[0])
    if not tree.exists():
        tmp = tree.with_name(tree.name + '.partial')
        if tmp.exists():
            raise RuntimeError('partial source extraction exists: ' + str(tmp))
        tmp.mkdir()
        topdir = pkg['upstream_name'] + '-' + version
        try:
            with tarfile.open(archive, 'r:*') as tf:
                for member in tf.getmembers():
                    parts = Path(member.name)
                    if parts.is_absolute() or not parts.parts or parts.parts[0] != topdir or '..' in parts.parts:
                        raise RuntimeError('unsafe archive member ' + member.name)
                    if not (member.isdir() or member.isfile() or member.issym()):
                        raise RuntimeError('unsupported archive member ' + member.name)
                tf.extractall(tmp, filter='data')
            if not (tmp / topdir / 'configure').is_file():
                raise RuntimeError('source configure missing')
            tmp.rename(tree)
        finally:
            if tmp.exists():
                import shutil
                shutil.rmtree(tmp)
    source_dir = tree / (pkg['upstream_name'] + '-' + version)
    if not (source_dir / 'configure').is_file():
        raise RuntimeError('source cache invalid')
    run_root = state / 'work' / name
    run_root.mkdir(parents=True, exist_ok=True)
    index = 1
    while (run_root / f'run-{index:03d}').exists():
        index += 1
    work = run_root / f'run-{index:03d}'
    (work / 'build').mkdir(parents=True)
    (work / 'stage').mkdir()
    (work / 'src-tree').mkdir()
    log = work / 'build.log'
    target = manifest['target']
    variables = {
        'target': target, 'version': version,
        'jobs': str(min(os.cpu_count() or 2, 8)),
        'cc': '/toolchain/usr/bin/' + target + '-gcc --sysroot=/toolchain -fno-link-libatomic',
        'cxx': '/toolchain/usr/bin/' + target + '-g++ --sysroot=/toolchain',
        'ldflags': '-B/toolchain/usr/lib64/ -L/toolchain/usr/lib64 -L/toolchain/lib64',
    }
    # Install source tree as a read-only nested mount rather than copying it.
    guest = common.sandbox(root, work, source_dir)
    for step in recipe['steps']:
        if set(step) != {'name','argv'}:
            raise RuntimeError('invalid recipe step')
        argv = [s.format_map(variables) for s in step['argv']]
        print(f'[temp-tools] {name}: step={step["name"]}', flush=True)
        common.run(guest + argv, log)
    evidence = common.install(work / 'stage', root)
    if not evidence:
        raise RuntimeError('empty installed package')
    for binary in recipe['validation']['chroot_executables']:
        if not (root / binary.lstrip('/')).is_file():
            raise RuntimeError('missing installed executable: ' + binary)
        validate_in_root(root, work, binary)
    if name == 'native-gcc':
        compiler_smoke(root, work)
    common.save(stamp, {'schema_version':1,'phase':'temp-tools','package':name,
                        'status':'complete','manifest_sha256':signature,
                        'source_sha256':common.sha(archive),'installed':evidence})
    print(f'[temp-tools] {name}: COMPLETE; {len(evidence)} files/links verified', flush=True)

if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise RuntimeError('usage: temp_native_cross.py PROJECT PACKAGE')
        main(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, KeyError, RuntimeError, tarfile.TarError, subprocess.TimeoutExpired) as e:
        print('[temp-tools] native-cross ERROR:', e, file=sys.stderr, flush=True)
        sys.exit(1)
