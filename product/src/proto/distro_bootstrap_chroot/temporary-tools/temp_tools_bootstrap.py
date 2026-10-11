#!/usr/bin/env python3
"""Prototype temp-tools bootstrap: verified cross archive to resumable Bash root."""
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

TARGET = 'x86_64-distro-linux-gnu'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    os.replace(tmp, path)

def check_directory(path):
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise RuntimeError(f'unsafe directory: {path}')

def empty(path):
    return not path.exists() or not any(path.iterdir())

def archive_members(tf):
    members = tf.getmembers()
    names = set()
    for member in members:
        name = member.name
        p = Path(name)
        if p.is_absolute() or not p.parts or any(part in ('..', '.') for part in p.parts):
            raise RuntimeError(f'unsafe archive member: {name}')
        if name in names:
            raise RuntimeError(f'duplicate archive member: {name}')
        names.add(name)
        if not (member.isfile() or member.isdir() or member.issym()):
            raise RuntimeError(f'unsupported archive member: {name}')
        if member.issym():
            link = Path(member.linkname)
            if link.is_absolute():
                raise RuntimeError(f'absolute archive symlink: {name}')
            parts = list(p.parent.parts)
            for component in link.parts:
                if component == '..':
                    if not parts:
                        raise RuntimeError(f'escaping archive symlink: {name}')
                    parts.pop()
                elif component != '.':
                    parts.append(component)
    return members

def run(cmd, *, logfile=None, timeout=7200, env=None):
    if logfile is None:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)
        if p.returncode:
            raise RuntimeError(f'command failed ({p.returncode}): {cmd!r}: {p.stderr[-1600:]}')
        return p.stdout
    with logfile.open('a') as out:
        out.write('STEP ' + ' '.join(map(str, cmd)) + '\n')
        out.flush()
        p = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, timeout=timeout, env=env, check=False)
    if p.returncode:
        raise RuntimeError(f'command failed ({p.returncode}); inspect {logfile}')

def sandbox(root, workspace):
    if shutil.which('bwrap') is None:
        raise RuntimeError('bubblewrap is required')
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-user', '--unshare-pid',
           '--unshare-net', '--unshare-ipc', '--unshare-uts', '--proc', '/proc', '--dev', '/dev',
           '--tmpfs', '/tmp', '--dir', '/run', '--ro-bind', str(root), '/toolchain',
           '--bind', str(workspace), '/work', '--chdir', '/work/build', '--clearenv',
           '--setenv', 'PATH', '/toolchain/bin:/usr/bin:/bin', '--setenv', 'HOME', '/work',
           '--setenv', 'LC_ALL', 'C']
    for part in ('usr', 'bin', 'sbin', 'lib', 'lib64', 'etc'):
        if (Path('/') / part).exists():
            cmd.extend(['--ro-bind', '/' + part, '/' + part])
    return cmd + ['--']

def validate_bash(root, work):
    for name, dest in (('bin', 'usr/bin'), ('sbin', 'usr/sbin'),
                       ('lib', 'usr/lib'), ('lib64', 'usr/lib64')):
        if not (root / name).is_symlink() or os.readlink(root / name) != dest:
            raise RuntimeError('invalid imported merged-/usr symlink: ' + name)
    binary = root / 'bin/bash'
    if not binary.is_file() or binary.is_symlink():
        raise RuntimeError('Bash executable missing or not regular')
    prog = run(['readelf', '-l', str(binary)])
    if '[Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]' not in prog:
        raise RuntimeError('unexpected Bash ELF interpreter')
    dynamic = run(['readelf', '-d', str(binary)])
    needed = re.findall(r'\(NEEDED\).*?\[([^]]+)\]', dynamic)
    if not needed or 'libc.so.6' not in needed:
        raise RuntimeError(f'unexpected Bash dependencies: {needed}')
    for lib in needed:
        if '/' in lib or not any((root / p / lib).is_file() for p in ('lib64', 'usr/lib64', 'lib', 'usr/lib')):
            raise RuntimeError(f'Bash runtime dependency absent from root: {lib}')
    # A new mount namespace presents the imported root as /, without host /usr mounts.
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-user', '--unshare-pid',
           '--unshare-net', '--unshare-ipc', '--unshare-uts', '--bind', str(root), '/',
           '--chdir', '/', '--clearenv', '--setenv', 'PATH', '/bin:/usr/bin',
           '--', '/bin/bash', '--noprofile', '--norc', '-c',
           'printf "Distro Bash: %s\\n" "$BASH_VERSION"; test -r /usr/include/linux/version.h']
    output = run(cmd, timeout=90)
    return {'bash_sha256': sha(binary), 'needed': needed,
            'namespace_execution': 'passed', 'stdout': output.strip(),
            'chroot_command': 'sudo chroot <project>/root /bin/bash --noprofile --norc'}

def main(project, cross_archive):
    if os.geteuid() == 0:
        raise RuntimeError('run as a regular user')
    project = Path(project).expanduser().resolve()
    if project in (Path('/'), Path.home().resolve()):
        raise RuntimeError('unsafe project root')
    archive = Path(cross_archive).expanduser().resolve(strict=True)
    if not archive.is_file():
        raise RuntimeError('cross compiler archive missing')
    root = project / 'root'
    state = project / '.distro-bootstrap'
    check_directory(root)
    check_directory(state)
    archive_digest = sha(archive)
    report = Path(str(archive) + '.json')
    if not report.is_file():
        raise RuntimeError(f'cross-toolchain export report missing: {report}')
    export = json.loads(report.read_text())
    if (export.get('status') != 'passed' or export.get('phase') != 'cross-toolchain'
            or export.get('target') != TARGET or export.get('archive_sha256') != archive_digest):
        raise RuntimeError('cross-toolchain export report identity/digest mismatch')
    marker = state / 'temp-tools-import.json'
    if marker.exists():
        previous = json.loads(marker.read_text())
        if previous.get('stage') != 'temp-tools' or previous.get('cross_archive_sha256') != archive_digest or previous.get('status') != 'complete':
            raise RuntimeError('existing temp-tools state does not match archive')
        if not root.is_dir() or empty(root):
            raise RuntimeError('existing temp-tools root missing or empty')
        for relative, expected in previous.get('files', {}).items():
            if sha(root / relative) != expected:
                raise RuntimeError('imported toolchain has changed: ' + relative)
        print('[temp-tools] resume: verified imported cross-toolchain', flush=True)
    else:
        if not empty(root) or not empty(state):
            raise RuntimeError('root/ and .distro-bootstrap/ must both be empty for a fresh temp-tools run')
        print('[temp-tools] importing cross-toolchain', flush=True)
        with tarfile.open(archive, 'r:xz') as tf:
            members = archive_members(tf)
            project.mkdir(parents=True, exist_ok=True)
            root.mkdir(exist_ok=True)
            state.mkdir(exist_ok=True)
            tf.extractall(root, members=members, filter='data')
        required = ('bin/' + TARGET + '-gcc', 'bin/' + TARGET + '-g++',
                    'lib64/libc.so.6', 'lib64/ld-linux-x86-64.so.2',
                    'usr/include/linux/version.h')
        evidence = {}
        for relative in required:
            path = root / relative
            if not path.is_file():
                raise RuntimeError(f'extracted prerequisite missing: {relative}')
            evidence[relative] = sha(path)
        save(marker, {'schema_version': 1, 'stage': 'temp-tools', 'status': 'complete',
                      'cross_archive_sha256': archive_digest, 'files': evidence})
    stamp = state / 'stamps/bash.json'
    if stamp.exists():
        prior = json.loads(stamp.read_text())
        if prior.get('status') != 'complete' or prior.get('cross_archive_sha256') != archive_digest:
            raise RuntimeError('Bash completion stamp invalid')
        proof = validate_bash(root, state)
        if prior.get('bash_sha256') != proof['bash_sha256']:
            raise RuntimeError('Bash content changed after completion')
        print('[temp-tools] bash: SKIP verified stamp; namespace execution PASS', flush=True)
        return
    if (root / 'bin/bash').exists():
        raise RuntimeError('untracked Bash installation in root; refusing overwrite')
    version_text = run(['/usr/bin/bash', '--version'])
    match = re.search(r'version (\d+\.\d+)', version_text)
    if not match:
        raise RuntimeError('cannot resolve host Bash major.minor version')
    version = match.group(1)
    url = f'https://ftp.gnu.org/gnu/bash/bash-{version}.tar.gz'
    runs = state / 'work/bash'
    runs.mkdir(parents=True, exist_ok=True)
    number = 1
    while (runs / f'run-{number:03d}').exists():
        number += 1
    work = runs / f'run-{number:03d}'
    work.mkdir()
    (work / 'build').mkdir()
    (work / 'prefix').mkdir()
    (work / 'src').mkdir()
    logfile = work / 'build.log'
    tar_path = work / 'source.tar.gz'
    print(f'[temp-tools] bash {version}: download and build; log={logfile}', flush=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as response, tar_path.open('wb') as dest:
            shutil.copyfileobj(response, dest)
        source_digest = sha(tar_path)
        with tarfile.open(tar_path, 'r:gz') as tf:
            tf.extractall(work / 'src', filter='data')
        source = work / 'src' / f'bash-{version}'
        if not source.is_dir():
            raise RuntimeError('Bash source directory missing')
        # Explicit target compiler/sysroot. No target-side host headers/libraries.
        cc = f'/toolchain/bin/{TARGET}-gcc --sysroot=/toolchain -fno-link-libatomic'
        ldflags = '-B/toolchain/usr/lib64/ -L/toolchain/usr/lib64 -L/toolchain/lib64'
        env = {'CC': cc, 'CFLAGS': '-O2', 'LDFLAGS': ldflags,
               'AR': f'/toolchain/bin/{TARGET}-ar', 'RANLIB': f'/toolchain/bin/{TARGET}-ranlib'}
        guest = work / 'steps.py'
        guest.write_text('''import os, subprocess, sys\ne = os.environ.copy()\ne.update(%r)\nsteps = [\n  ['/work/src/bash-%s/configure', '--host=%s', '--build=x86_64-pc-linux-gnu', '--prefix=/usr', '--bindir=/bin', '--without-bash-malloc', '--disable-nls'],\n  ['make', '-j%s'],\n  ['make', 'install', 'DESTDIR=/work/prefix'],\n]\nfor command in steps:\n print('STEP', ' '.join(command), flush=True)\n rc = subprocess.call(command, env=e)\n if rc: sys.exit(rc)\n''' % (env, version, TARGET, os.cpu_count() or 1))
        run(sandbox(root, work) + ['/usr/bin/python3', '/work/steps.py'], logfile=logfile)
        staged = work / 'prefix/bin/bash'
        if not staged.is_file():
            raise RuntimeError('staged Bash executable not found')
        # Only Bash and its license-bearing docs are staged; initially install the binary alone.
        shutil.copy2(staged, root / 'bin/bash')
        proof = validate_bash(root, work)
        save(stamp, {'schema_version': 1, 'status': 'complete', 'package': 'bash',
                     'cross_archive_sha256': archive_digest, 'source_url': url,
                     'source_sha256': source_digest, **proof})
        print('[temp-tools] bash: COMPLETE; isolated root execution PASS', flush=True)
        print('[temp-tools] real chroot entry: sudo chroot ' + str(root) + ' /bin/bash --noprofile --norc', flush=True)
    except Exception:
        # If Bash was installed but not stamped, do not allow automatic resume to overwrite it.
        raise

if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise RuntimeError('usage: temp_tools_bootstrap.py PROJECT CROSS_ARCHIVE')
        main(sys.argv[1], sys.argv[2])
    except (OSError, RuntimeError, ValueError, tarfile.TarError, subprocess.TimeoutExpired) as error:
        print('[temp-tools] ERROR:', error, file=sys.stderr, flush=True)
        raise SystemExit(1)
