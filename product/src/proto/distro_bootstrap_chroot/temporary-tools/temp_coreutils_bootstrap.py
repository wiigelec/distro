#!/usr/bin/env python3
"""Cross-build GNU Coreutils with the imported Distro toolchain into root/.

Temporary bridge before the chroot has its own native C compiler and make.
Not a native-chroot build: host utilities run in an isolated cross-build sandbox.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'temporary-tools-manifest.json'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for buf in iter(lambda: f.read(1024 * 1024), b''):
            h.update(buf)
    return h.hexdigest()

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, sort_keys=True, indent=2) + '\n')
    os.replace(tmp, path)

def run(cmd, log, timeout=7200):
    with log.open('a') as f:
        f.write('STEP ' + ' '.join(cmd) + '\n')
        f.flush()
        p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    if p.returncode:
        raise RuntimeError(f'command failed ({p.returncode}); inspect {log}')

def obtain(url, output, expected):
    if output.is_file():
        if sha(output) != expected:
            raise RuntimeError('cached source checksum mismatch: ' + str(output))
        return
    temp = output.with_name(output.name + '.partial')
    try:
        with urllib.request.urlopen(url, timeout=120) as response, temp.open('wb') as f:
            shutil.copyfileobj(response, f)
        if sha(temp) != expected:
            raise RuntimeError('downloaded source checksum mismatch: ' + str(temp))
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)

def extract(archive, destination, topdir):
    if destination.exists():
        if not (destination / topdir / 'configure').is_file():
            raise RuntimeError('incomplete source tree: ' + str(destination))
        return
    temp = destination.with_name(destination.name + '.partial')
    if temp.exists():
        raise RuntimeError('incomplete extraction: ' + str(temp))
    temp.mkdir(parents=True)
    try:
        with tarfile.open(archive, 'r:xz') as tf:
            for m in tf.getmembers():
                p = Path(m.name)
                if p.is_absolute() or not p.parts or p.parts[0] != topdir or '..' in p.parts:
                    raise RuntimeError('unsafe archive path: ' + m.name)
                if not (m.isdir() or m.isfile() or m.issym()):
                    raise RuntimeError('unsupported archive entry: ' + m.name)
            tf.extractall(temp, filter='data')
        if not (temp / topdir / 'configure').is_file():
            raise RuntimeError('configure missing after extraction')
        temp.rename(destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)

def sandbox(root, work, source_dir):
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-user',
           '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts',
           '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/run',
           '--ro-bind', str(root), '/toolchain', '--bind', str(work), '/work',
           '--ro-bind', str(source_dir), '/work/src',
           '--chdir', '/work/build', '--clearenv',
           '--setenv', 'HOME', '/work', '--setenv', 'LC_ALL', 'C',
           '--setenv', 'PATH', '/toolchain/usr/bin:/usr/bin:/bin']
    for name in ('usr', 'bin', 'sbin', 'lib', 'lib64', 'etc'):
        if (Path('/') / name).exists():
            cmd += ['--ro-bind', '/' + name, '/' + name]
    return cmd + ['--']

def install(stage, root):
    """Preflight staged paths and reject overwrites; then copy selected payload."""
    src = stage / 'usr'
    if not src.is_dir() or src.is_symlink():
        raise RuntimeError('Coreutils staged /usr missing')
    entries = []
    for path in sorted(src.rglob('*')):
        rel = path.relative_to(stage)
        if rel.as_posix() == 'usr/share/info/dir':
            continue
        dst = root / rel
        if path.is_symlink():
            target = os.readlink(path)
            if os.path.isabs(target):
                raise RuntimeError('absolute staged symlink: ' + str(rel))
            # A staged link must resolve within the final root.
            if not (dst.parent / target).resolve(strict=False).is_relative_to(root.resolve()):
                raise RuntimeError('escaping staged symlink: ' + str(rel))
            kind = 'link'
        elif path.is_dir():
            kind = 'dir'
        elif path.is_file():
            kind = 'file'
        else:
            raise RuntimeError('unsupported staged entry: ' + str(rel))
        parent = dst.parent
        while parent != root:
            if parent.is_symlink():
                raise RuntimeError('symlink in install path: ' + str(parent))
            parent = parent.parent
        if kind == 'dir':
            if dst.is_symlink() or (dst.exists() and not dst.is_dir()):
                raise RuntimeError('install directory conflict: ' + str(rel))
        elif dst.exists() or dst.is_symlink():
            raise RuntimeError('install file collision: ' + str(rel))
        entries.append((path, dst, kind, rel))
    created = []
    evidence = {}
    try:
        for source, dst, kind, rel in entries:
            if kind == 'dir':
                if not dst.exists():
                    dst.mkdir(parents=True)
                    created.append(dst)
            elif kind == 'link':
                dst.parent.mkdir(parents=True, exist_ok=True)
                target = os.readlink(source)
                dst.symlink_to(target)
                created.append(dst)
                evidence[str(rel)] = {'link': target}
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dst)
                created.append(dst)
                evidence[str(rel)] = {'sha256': sha(dst)}
    except Exception:
        for p in reversed(created):
            if p.is_file() or p.is_symlink():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        raise
    return evidence

def main(project):
    if os.geteuid() == 0:
        raise RuntimeError('run as regular user')
    project = Path(project).expanduser().resolve()
    root, state = project / 'root', project / '.distro-bootstrap'
    if root.is_symlink() or state.is_symlink() or not root.is_dir() or not state.is_dir():
        raise RuntimeError('invalid target root or state')
    if not (root / 'usr/bin/bash').is_file():
        raise RuntimeError('run Bash temp-tools bootstrap first')
    if not (state / 'temp-tools-import.json').is_file():
        raise RuntimeError('verified cross-toolchain import marker missing')
    cfg = json.loads(MANIFEST.read_text())
    if cfg.get('phase') != 'temp-tools' or cfg.get('target') != 'x86_64-distro-linux-gnu':
        raise RuntimeError('invalid temp-tools manifest')
    matches = [p for p in cfg['packages'] if p['name'] == 'coreutils']
    if len(matches) != 1 or matches[0].get('state') != 'executable':
        raise RuntimeError('Coreutils manifest entry missing or not executable')
    pkg = matches[0]
    recipe_path = (HERE / pkg['recipe']).resolve()
    if not recipe_path.is_relative_to(HERE) or not recipe_path.is_file():
        raise RuntimeError('invalid Coreutils recipe reference')
    recipe = json.loads(recipe_path.read_text())
    if recipe.get('name') != 'coreutils' or recipe.get('phase') != 'temp-tools':
        raise RuntimeError('Coreutils recipe identity mismatch')
    version = pkg['version']
    source = pkg['source']
    if not re.fullmatch('[0-9a-f]{64}', source['sha256']):
        raise RuntimeError('unpinned source')
    if source['url'] != f'https://ftp.gnu.org/gnu/coreutils/coreutils-{version}.tar.xz':
        raise RuntimeError('unapproved source URL')
    stamp = state / 'stamps/coreutils.json'
    recipe_digest = hashlib.sha256((sha(recipe_path) + ':' + json.dumps(pkg, sort_keys=True)).encode()).hexdigest()
    if stamp.is_file():
        record = json.loads(stamp.read_text())
        if record.get('manifest_sha256') != recipe_digest or record.get('status') != 'complete':
            raise RuntimeError('Coreutils stamp inconsistent; use clean target for changed inputs')
        for relative, proof in record['installed'].items():
            dest = root / relative
            if 'sha256' in proof and (not dest.is_file() or sha(dest) != proof['sha256']):
                raise RuntimeError('Coreutils installed file changed: ' + relative)
            if 'link' in proof and (not dest.is_symlink() or os.readlink(dest) != proof['link']):
                raise RuntimeError('Coreutils symlink changed: ' + relative)
        print('[temp-tools] coreutils: SKIP verified stamp', flush=True)
        return
    if (root / 'usr/bin/mkdir').exists():
        raise RuntimeError('untracked Coreutils mkdir exists; refusing overwrite')
    cache = state / 'sources'
    cache.mkdir(exist_ok=True)
    archive = cache / f'coreutils-{version}.tar.xz'
    print('[temp-tools] coreutils: downloading and verifying source', flush=True)
    obtain(source['url'], archive, source['sha256'])
    extracted = cache / f'extracted-coreutils-{version}'
    extract(archive, extracted, f'coreutils-{version}')
    run_root = state / 'work/coreutils'
    run_root.mkdir(parents=True, exist_ok=True)
    number = 1
    while (run_root / f'run-{number:03d}').exists():
        number += 1
    work = run_root / f'run-{number:03d}'
    (work / 'build').mkdir(parents=True)
    (work / 'stage').mkdir()
    (work / 'src').mkdir()
    log = work / 'build.log'
    target = cfg['target']
    cc = f'/toolchain/usr/bin/{target}-gcc --sysroot=/toolchain -fno-link-libatomic'
    guest = sandbox(root, work, extracted / f'coreutils-{version}')
    variables = {'target': target, 'version': version, 'jobs': str(min(os.cpu_count() or 2, 8)),
                 'cc': cc, 'ldflags': '-B/toolchain/usr/lib64/ -L/toolchain/usr/lib64 -L/toolchain/lib64'}
    print('[temp-tools] coreutils: executing manifest recipe with target cross compiler', flush=True)
    for step in recipe['steps']:
        if not isinstance(step, dict) or set(step) != {'name', 'argv'}:
            raise RuntimeError('invalid Coreutils recipe step')
        argv = [arg.format_map(variables) for arg in step['argv']]
        if not argv or any(not isinstance(arg, str) or not arg for arg in argv):
            raise RuntimeError('invalid Coreutils recipe argv')
        print('[temp-tools] coreutils: step=' + step['name'], flush=True)
        run(guest + argv, log)
    installed = install(work / 'stage', root)
    if not (root / 'usr/bin/mkdir').is_file() or not (root / 'usr/bin/ls').is_file():
        raise RuntimeError('Coreutils install missing mkdir/ls')
    verify = ['bwrap', '--die-with-parent', '--new-session', '--unshare-user',
              '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts',
              '--bind', str(root), '/', '--proc', '/proc', '--dev', '/dev',
              '--tmpfs', '/tmp', '--clearenv', '--setenv', 'PATH', '/usr/bin:/bin',
              '--', '/bin/bash', '--noprofile', '--norc', '-c',
              'mkdir --version >/dev/null && ls --version >/dev/null && test -x /usr/bin/cp']
    run(verify, log, timeout=90)
    save(stamp, {'schema_version': 1, 'phase': 'temp-tools', 'package': 'coreutils',
                 'status': 'complete', 'manifest_sha256': recipe_digest,
                 'source_sha256': sha(archive), 'installed': installed})
    print(f'[temp-tools] coreutils: COMPLETE; {len(installed)} files and links; mkdir/ls verified inside chroot', flush=True)

if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise RuntimeError('usage: temp_coreutils_bootstrap.py PROJECT')
        main(sys.argv[1])
    except (OSError, ValueError, RuntimeError, tarfile.TarError, subprocess.TimeoutExpired) as e:
        print('[temp-tools] coreutils ERROR:', e, file=sys.stderr, flush=True)
        sys.exit(1)
