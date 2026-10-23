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
import shutil
import subprocess
import sys
import tarfile

from . import temp_cross_package as common

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



def prepare_gcc_prerequisites(pkg, cache, work, source_dir):
    """Pin GCC's supported in-tree prerequisite sources without mutating its cache."""
    deps = pkg.get('build_prerequisites')
    if not isinstance(deps, list) or [x.get('name') for x in deps] != ['gmp', 'mpfr', 'mpc']:
        raise RuntimeError('GCC prerequisite source manifest missing or reordered')
    deps_root = work / 'deps'
    deps_root.mkdir()
    overlay = work / 'gcc-overlay'
    overlay.mkdir()
    # Symlink farm, not a copy: GCC sources stay read-only, while the 3
    # additional source trees are exposed under the conventional names.
    for entry in source_dir.iterdir():
        if entry.name in ('gmp', 'mpfr', 'mpc'):
            raise RuntimeError('GCC source already contains a prerequisite directory')
        (overlay / entry.name).symlink_to('/gcc-upstream/' + entry.name)
    for item in deps:
        name, version = item['name'], item['version']
        filename = item['url'].rsplit('/',1)[-1]
        if filename not in (f'{name}-{version}.tar.gz', f'{name}-{version}.tar.bz2'):
            raise RuntimeError('unrecognized prerequisite archive name')
        if item['url'] != f'https://gcc.gnu.org/pub/gcc/infrastructure/{filename}':
            raise RuntimeError('unapproved GCC prerequisite origin')
        expected = item['sha512']
        if not re.fullmatch('[a-f0-9]{128}', expected):
            raise RuntimeError('invalid prerequisite SHA512')
        archive = cache / filename
        if archive.exists():
            if hashlib.sha512(archive.read_bytes()).hexdigest() != expected:
                raise RuntimeError('cached GCC prerequisite checksum mismatch: ' + filename)
        else:
            import urllib.request, shutil
            tmp = archive.with_name(archive.name + '.partial')
            try:
                with urllib.request.urlopen(item['url'], timeout=120) as response, tmp.open('wb') as output:
                    shutil.copyfileobj(response, output)
                if hashlib.sha512(tmp.read_bytes()).hexdigest() != expected:
                    raise RuntimeError('downloaded GCC prerequisite checksum mismatch: ' + filename)
                os.replace(tmp, archive)
            finally:
                tmp.unlink(missing_ok=True)
        extracted = cache / ('gcc-prerequisite-' + name + '-' + version)
        topdir = name + '-' + version
        if not extracted.exists():
            temp = extracted.with_name(extracted.name + '.partial')
            if temp.exists():
                raise RuntimeError('incomplete prior extraction: ' + str(temp))
            temp.mkdir()
            try:
                with tarfile.open(archive, 'r:*') as tf:
                    for member in tf.getmembers():
                        p = Path(member.name)
                        if p.is_absolute() or not p.parts or p.parts[0] != topdir or '..' in p.parts:
                            raise RuntimeError('unsafe prerequisite member: ' + member.name)
                        if not (member.isdir() or member.isfile() or member.issym()):
                            raise RuntimeError('unsupported prerequisite archive entry: ' + member.name)
                    tf.extractall(temp, filter='data')
                if not (temp / topdir / 'configure').is_file():
                    raise RuntimeError('prerequisite configure missing: ' + name)
                temp.rename(extracted)
            finally:
                if temp.exists():
                    import shutil
                    shutil.rmtree(temp)
        package_dir = extracted / topdir
        if not (package_dir / 'configure').is_file():
            raise RuntimeError('incomplete prerequisite cache: ' + name)
        (deps_root / name).symlink_to('/gcc-prerequisites/' + name)
        (overlay / name).symlink_to('/deps/' + name)
        print(f'[temp-tools] native-gcc: {name} {version} SHA512 verified', flush=True)
    return overlay, deps_root, {item['name']: cache / ('gcc-prerequisite-' + item['name'] + '-' + item['version']) / (item['name'] + '-' + item['version']) for item in deps}

def installed_native_gcc_from_failed_run(root, state):
    """Recover only byte-identical native files left by run-005.

    Imported archive entries do not belong to this recovery set. Verify the
    entire old native payload before allowing any of it to be replaced.
    """
    work = state / 'work/native-gcc/run-005'
    stage = work / 'stage/usr'
    if not stage.is_dir() or not (work / 'native-smoke.log').is_file():
        raise RuntimeError('missing failed native GCC run-005 stage/smoke evidence')
    smoke = (work / 'native-smoke.log').read_text(errors='replace')
    if 'libisl.so.23' not in smoke or 'error while loading shared libraries' not in smoke:
        raise RuntimeError('run-005 is not the expected failed native GCC validation')
    marker = json.loads((state / 'temp-tools-import.json').read_text())
    archive = state.parent / 'artifacts/cross-toolchain-root.tar.xz'
    if common.sha(archive) != marker.get('cross_archive_sha256'):
        raise RuntimeError('import archive changed during native GCC recovery')
    imported = set()
    with tarfile.open(archive, 'r:xz') as tf:
        for member in tf:
            if member.isfile() or member.issym() or member.islnk():
                imported.add(member.name.removeprefix('./'))
    proof = {}
    for source in sorted(stage.rglob('*')):
        rel = source.relative_to(work / 'stage').as_posix()
        if rel == 'usr/share/info/dir' or source.is_dir():
            continue
        if rel in imported:
            continue
        destination = root / rel
        if source.is_symlink():
            if not destination.is_symlink() or os.readlink(source) != os.readlink(destination):
                raise RuntimeError('modified recovered native GCC symlink: ' + rel)
            proof[rel] = {'link': os.readlink(source)}
        elif source.is_file():
            if destination.is_symlink() or not destination.is_file() or common.sha(source) != common.sha(destination):
                raise RuntimeError('modified recovered native GCC file: ' + rel)
            proof[rel] = {'sha256': common.sha(source)}
        else:
            raise RuntimeError('invalid recovered native GCC entry: ' + rel)
    if not proof or 'usr/bin/gcc' not in proof:
        raise RuntimeError('incomplete failed native GCC staged payload')
    print(f'[temp-tools] native-gcc: verified {len(proof)} unstamped run-005 files for recovery', flush=True)
    return proof


def rollback_native_gcc(created, backup, root):
    """Undo new native files and restore exactly the verified prior payload."""
    for destination in reversed(created):
        if destination.is_symlink() or destination.is_file():
            destination.unlink()
        elif destination.is_dir() and not any(destination.iterdir()):
            destination.rmdir()
    for relative, src in backup.items():
        dst = root / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            dst.symlink_to(os.readlink(src))
        else:
            import shutil
            shutil.copy2(src, dst)


def install_native_gcc(stage, root, state, work, prior_native):
    """Transactionally install native GCC, protecting imported cross files.

    Never overwrite imported files. Previous native files are only replaceable
    after exact verification against the failed run-005 staged payload.
    """
    marker = state / 'temp-tools-import.json'
    archive = state.parent / 'artifacts/cross-toolchain-root.tar.xz'
    if not marker.is_file() or not archive.is_file():
        raise RuntimeError('missing verified cross-toolchain import/archive')
    record = json.loads(marker.read_text())
    if (record.get('stage') != 'temp-tools' or record.get('status') != 'complete'
            or common.sha(archive) != record.get('cross_archive_sha256')):
        raise RuntimeError('cross-toolchain archive differs from verified import')
    source_root = stage / 'usr'
    if not source_root.is_dir() or source_root.is_symlink():
        raise RuntimeError('missing native GCC staged /usr')
    collisions = set()
    for path in source_root.rglob('*'):
        if (path.is_file() or path.is_symlink()) and ((root / path.relative_to(stage)).exists() or (root / path.relative_to(stage)).is_symlink()):
            collisions.add(path.relative_to(stage).as_posix())
    prior_owned = set()
    with tarfile.open(archive, 'r:xz') as tf:
        for member in tf:
            relative = member.name.removeprefix('./')
            if relative not in collisions:
                continue
            if relative in prior_owned:
                raise RuntimeError('duplicate imported path: ' + relative)
            destination = root / relative
            if member.isfile():
                source = tf.extractfile(member)
                if source is None or not destination.is_file() or destination.is_symlink():
                    raise RuntimeError('modified imported file: ' + relative)
                digest = hashlib.sha256()
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
                if common.sha(destination) != digest.hexdigest():
                    raise RuntimeError('modified imported file: ' + relative)
            elif member.issym():
                if not destination.is_symlink() or os.readlink(destination) != member.linkname:
                    raise RuntimeError('modified imported symlink: ' + relative)
            elif member.islnk():
                raise RuntimeError('unsupported imported hardlink collision: ' + relative)
            else:
                raise RuntimeError('invalid imported archive member: ' + relative)
            prior_owned.add(relative)
    if prior_owned.intersection(prior_native):
        raise RuntimeError('recovered native GCC overlaps imported cross ownership')
    # The native driver and cross compiler use the same private GCC backend
    # directory. Only those compiler-internal paths may transition ownership.
    # Other imported cross-toolchain files remain immutable.
    private_prefix = 'usr/libexec/gcc/x86_64-distro-linux-gnu/16.2.0/'
    handoff = {rel for rel in prior_owned if rel.startswith(private_prefix)}
    if private_prefix + 'cc1' not in handoff:
        raise RuntimeError('imported cross-GCC cc1 not available for guarded handoff')
    entries = []
    skipped = 0
    for source in sorted(source_root.rglob('*')):
        rel = source.relative_to(stage).as_posix()
        if rel == 'usr/share/info/dir':
            continue
        destination = root / rel
        if source.is_symlink():
            link = os.readlink(source)
            if os.path.isabs(link) or not (destination.parent / link).resolve(strict=False).is_relative_to(root.resolve()):
                raise RuntimeError('unsafe staged native GCC symlink: ' + rel)
            kind = 'link'
        elif source.is_dir():
            kind = 'dir'
        elif source.is_file():
            kind = 'file'
        else:
            raise RuntimeError('unsupported native GCC staged entry: ' + rel)
        parent = destination.parent
        while parent != root:
            if parent.is_symlink():
                raise RuntimeError('symlink in native GCC install path: ' + str(parent))
            parent = parent.parent
        if kind == 'dir':
            if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
                raise RuntimeError('native GCC directory collision: ' + rel)
        elif destination.exists() or destination.is_symlink():
            if rel in prior_owned and rel not in handoff:
                skipped += 1
                continue
            if rel not in prior_native and rel not in handoff:
                raise RuntimeError('unowned native GCC file collision: ' + rel)
        entries.append((source, destination, kind, rel))
    # Back up every old native file, including ones removed by the new recipe.
    backup_dir = work / 'recovery-backup'
    backup_dir.mkdir()
    backup = {}
    import shutil
    replaceable = set(prior_native) | {rel for _, _, kind, rel in entries
                                         if kind != 'dir' and rel in handoff}
    for rel in sorted(replaceable):
        src = root / rel
        dst = backup_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            dst.symlink_to(os.readlink(src))
        else:
            shutil.copy2(src, dst)
        backup[rel] = dst
    created = []
    installed = {}
    try:
        # Once fully backed up, remove only verified prior-native paths.
        for rel in sorted(replaceable):
            (root / rel).unlink()
        for source, destination, kind, rel in entries:
            if kind == 'dir':
                if not destination.exists():
                    destination.mkdir(parents=True)
                    created.append(destination)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if kind == 'link':
                    link = os.readlink(source)
                    destination.symlink_to(link)
                    installed[rel] = {'link': link}
                else:
                    shutil.copy2(source, destination)
                    installed[rel] = {'sha256': common.sha(destination)}
                created.append(destination)
    except Exception:
        rollback_native_gcc(created, backup, root)
        raise
    print(f'[temp-tools] native-gcc: preserved {skipped} verified imported paths; transitioned {len(replaceable - set(prior_native))} private GCC backends', flush=True)
    return installed, created, backup


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
    if name == 'native-gcc':
        # Its prior unstamped installation is independently verified before reuse.
        recovery_owned = installed_native_gcc_from_failed_run(root, state)
    else:
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
        'cxx': '/toolchain/usr/bin/' + target + '-g++ --sysroot=/toolchain -fno-link-libatomic',
        'ldflags': '-B/toolchain/usr/lib64/ -L/toolchain/usr/lib64 -L/toolchain/lib64',
    }
    # Install source tree as a read-only nested mount rather than copying it.
    if name == 'native-gcc':
        print('[temp-tools] native-gcc: verifying GMP/MPFR/MPC build prerequisites', flush=True)
        overlay, deps_root, dep_dirs = prepare_gcc_prerequisites(pkg, cache, work, source_dir)
        guest = common.sandbox(root, work, overlay)
        # The overlay contains absolute symlinks; explicitly mount their
        # read-only targets inside the sandbox before executing configure.
        guest = guest[:-1] + ['--ro-bind', str(source_dir), '/gcc-upstream',
                             '--ro-bind', str(deps_root), '/deps',
                             '--dir', '/gcc-prerequisites']
        for depname, deppath in dep_dirs.items():
            guest += ['--ro-bind', str(deppath), '/gcc-prerequisites/' + depname]
        # Export the target SystemTap probe override into every nested GCC
        # configure process. A top-level configure argument alone is not
        # inherited by the GCC subconfigure (which otherwise sees host headers).
        guest += ['--setenv', 'gcc_cv_sys_sdt_h', 'no', '--']
    elif name == 'make' and recipe['execution'] == 'native-root':
        # GNU Make can bootstrap itself without an existing make executable:
        # configure generates build.sh/build.cfg, then build.sh uses native GCC.
        # Host /usr, headers, shared libraries and compiler are never mounted.
        # A temporary read-only host awk is permitted for Autoconf's probes;
        # this is explicitly transient and is never installed in the root.
        # Bootstrap GNU Make once using a host gawk with only its explicit
        # shared-library dependencies copied into the ephemeral workspace.
        # Only the awk wrapper gets LD_LIBRARY_PATH; GCC/configure do not.
        awk = shutil.which('awk')
        if not awk:
            raise RuntimeError('host awk required to bootstrap GNU Make')
        awk_real = Path(awk).resolve(strict=True)
        deps = subprocess.run(['ldd', str(awk_real)], capture_output=True, text=True, check=True)
        host_libs = work / 'awk-libs'
        host_libs.mkdir()
        allowed = {'libreadline.so.8', 'libmpfr.so.6', 'libgmp.so.10',
                   'libncursesw.so.6', 'libtinfo.so.6'}
        copied = set()
        import shutil as _shutil
        for line in deps.stdout.splitlines():
            fields = line.strip().split()
            if len(fields) >= 3 and fields[1] == '=>':
                soname, location = fields[0], fields[2]
                if location == 'not':
                    raise RuntimeError('host awk has missing library: ' + soname)
                # ldd may report the ELF interpreter with '=>', too.
                # It is provided by the Distro root, not copied from the host.
                if soname.startswith('/') and Path(soname).name == 'ld-linux-x86-64.so.2':
                    if Path(location).name != 'ld-linux-x86-64.so.2':
                        raise RuntimeError('unexpected host awk ELF interpreter: ' + location)
                    continue
                if soname in ('libc.so.6', 'libm.so.6'):
                    continue  # Always use Distro libc and libm
                if soname not in allowed:
                    raise RuntimeError('unexpected host awk dependency: ' + soname)
                source = Path(location).resolve(strict=True)
                if not source.is_file() or not source.is_relative_to(Path('/usr/lib')):
                    raise RuntimeError('unsafe host awk dependency: ' + str(source))
                _shutil.copy2(source, host_libs / soname)
                copied.add(soname)
        if not copied:
            raise RuntimeError('host awk dependencies not resolved')
        _shutil.copy2(awk_real, work / 'host-awk-real')
        wrapper = work / 'host-awk'
        wrapper.write_text('#!/bin/sh\nLD_LIBRARY_PATH=/work/awk-libs exec /work/host-awk-real "$@"\n')
        wrapper.chmod(0o755)
        guest = ['bwrap', '--die-with-parent', '--new-session', '--unshare-user',
                 '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts',
                 '--bind', str(root), '/', '--bind', str(work), '/work',
                 '--ro-bind', str(source_dir), '/work/src',
                 '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
                 '--chdir', '/work/build', '--clearenv',
                 '--setenv', 'HOME', '/work', '--setenv', 'PATH', '/usr/bin:/bin',
                 '--setenv', 'LC_ALL', 'C', '--setenv', 'AWK', '/work/host-awk',
                 '--setenv', 'CONFIG_SHELL', '/bin/bash', '--']
        print('[temp-tools] make: native-root compilation using /usr/bin/gcc and GNU Make build.sh', flush=True)
    else:
        guest = common.sandbox(root, work, source_dir)
    for step in recipe['steps']:
        if set(step) != {'name','argv'}:
            raise RuntimeError('invalid recipe step')
        argv = [s.format_map(variables) for s in step['argv']]
        print(f'[temp-tools] {name}: step={step["name"]}', flush=True)
        common.run(guest + argv, log)
    if name == 'native-gcc':
        prior_native = recovery_owned
        evidence, created, backup = install_native_gcc(work / 'stage', root, state, work, prior_native)
    else:
        evidence = common.install(work / 'stage', root)
    try:
        if not evidence:
            raise RuntimeError('empty installed package')
        for binary in recipe['validation']['chroot_executables']:
            if not (root / binary.lstrip('/')).is_file():
                raise RuntimeError('missing installed executable: ' + binary)
            validate_in_root(root, work, binary)
        if name == 'native-gcc':
            compiler_smoke(root, work)
    except Exception:
        if name == 'native-gcc':
            rollback_native_gcc(created, backup, root)
        raise
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
