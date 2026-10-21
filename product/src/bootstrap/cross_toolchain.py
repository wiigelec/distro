#!/usr/bin/env python3
"""Build and verify an isolated target cross-toolchain from qualified sources.

The complete upstream inventory is frozen by preflight before any construction.
Recipes are explicit subprocess argument vectors, never interpreted as shell.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

from source_artifacts import SourceError, file_hash, select_component, verify_and_lock

TARGET = 'x86_64-distro-linux-gnu'
STAGES = ('binutils', 'gcc', 'linux-api-headers', 'glibc', 'libstdcxx')
ROOT = Path(__file__).resolve().parent


class ToolchainError(ValueError):
    """Required source, isolated operation, output, or verification is unavailable."""


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guard_path(path: Path, workspace: Path) -> Path:
    result = path.resolve()
    if result != workspace and not result.is_relative_to(workspace):
        raise ToolchainError('path escapes designated workspace')
    return result


def validate_recipe(recipe: dict, stage: str) -> None:
    if not isinstance(recipe, dict) or recipe.get('schema_version') != 1 or recipe.get('name') != stage:
        raise ToolchainError('invalid or mismatched recipe identity')
    if not isinstance(recipe.get('source_package'), str) or not recipe['source_package']:
        raise ToolchainError('recipe source ownership missing')
    if recipe.get('status') != 'experimental':
        raise ToolchainError('unexpected recipe status')
    steps = recipe.get('steps')
    if not isinstance(steps, list) or not steps:
        raise ToolchainError('recipe requires execution steps')
    for step in steps:
        if (not isinstance(step, dict) or not isinstance(step.get('name'), str) or
            not isinstance(step.get('argv'), list) or not step['argv'] or
            any(not isinstance(arg, str) or not arg for arg in step['argv'])):
            raise ToolchainError('invalid recipe argv')
    outputs = recipe.get('required_outputs')
    if not isinstance(outputs, list) or not outputs or any(not isinstance(p, str) or not p.startswith('/toolchain/') for p in outputs):
        raise ToolchainError('recipe must declare target-root output paths')


def sandbox_command(work: Path, root: Path, argv: list[str], *, command: str = 'bwrap') -> list[str]:
    """Provide a read-only host, bounded writable directories and no network."""
    if os.geteuid() == 0:
        raise ToolchainError('host build must not run as root')
    program = shutil.which(command)
    if not program:
        raise ToolchainError('Bubblewrap is required')
    for path in (work, root):
        if not path.is_dir():
            raise ToolchainError('build directory missing')
    args = [program, '--die-with-parent', '--new-session', '--unshare-user', '--unshare-pid',
            '--unshare-net', '--unshare-ipc', '--unshare-uts', '--proc', '/proc', '--dev', '/dev',
            '--tmpfs', '/tmp', '--dir', '/run', '--bind', str(work), '/work',
            '--bind', str(root), '/toolchain', '--chdir', '/work/build', '--clearenv',
            '--setenv', 'HOME', '/work', '--setenv', 'LC_ALL', 'C',
            '--setenv', 'PATH', '/toolchain/bin:/toolchain/usr/bin:/usr/bin:/bin']
    for name in ('usr', 'bin', 'sbin', 'lib', 'lib64', 'etc'):
        host = Path('/') / name
        if host.exists():
            args += ['--ro-bind', str(host), str(host)]
    return args + ['--'] + argv


def checked_source_extract(archive: Path, dest: Path) -> Path:
    """Reject unusual members and require exactly one source root directory."""
    if dest.exists():
        raise ToolchainError('source extraction destination already exists')
    dest.mkdir(parents=True)
    with tarfile.open(archive, 'r:*') as tar:
        members = tar.getmembers()
        if not members:
            raise ToolchainError('empty source archive')
        tops = set()
        for m in members:
            path = Path(m.name)
            if (path.is_absolute() or '..' in path.parts or not path.parts or
                    not (m.isdir() or m.isfile() or m.issym() or m.islnk())):
                raise ToolchainError('unsafe archive member')
            tops.add(path.parts[0])
        if len(tops) != 1:
            raise ToolchainError('source archive must have one root directory')
        tar.extractall(dest, filter='data')
    result = dest / next(iter(tops))
    if not result.is_dir():
        raise ToolchainError('source root missing')
    return result


def check_outputs(root: Path, recipe: dict, values: dict[str, str]) -> None:
    for entry in recipe['required_outputs']:
        guest = entry.format_map(values)
        relative = Path(guest).relative_to('/toolchain')
        if not (root / relative).is_file():
            raise ToolchainError('required toolchain output missing: ' + guest)


def run_stage(stage: str, baseline: dict, cache: Path, locks: Path, root: Path,
              work_base: Path, *, jobs: int, offline: bool = False,
              runner=subprocess.run, keyring: Path | None = None) -> dict:
    recipe_path = ROOT / 'recipes' / (stage + '.json')
    recipe = read_json(recipe_path)
    validate_recipe(recipe, stage)
    source_owner = recipe['source_package']
    source, upstream = select_component(baseline, source_owner)
    version = upstream['version']
    if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+_~-]*', version):
        raise ToolchainError('invalid reviewed source release')
    recipe_hash = digest(recipe_path)
    source_recipe_path = ROOT / 'recipes' / (source_owner + '.json')
    source_hash = digest(source_recipe_path)
    lock = verify_and_lock(baseline, source_owner, cache, locks,
                           recipe_sha256=source_hash, offline=offline, keyring=keyring)
    if lock.get('identity', {}).get('baseline_sha256') != baseline['baseline_sha256']:
        raise ToolchainError('source lock does not match execution baseline')
    filename = lock['identity']['source']['filename']
    archive = cache / (source_owner + '-' + filename)
    if file_hash(archive, lock['checksum_algorithm']) != lock['digest']:
        raise ToolchainError('source archive no longer matches verified lock')
    work = work_base / stage
    if work.exists():
        raise ToolchainError('work directory exists; preserve evidence and use a fresh work directory')
    work.mkdir(parents=True)
    (work / 'build').mkdir()
    source_dir = checked_source_extract(archive, work / 'src')
    values = {'target': TARGET, 'version': version, 'jobs': str(jobs), 'source': '/work/src/' + source_dir.name}
    log_path = work / 'build.log'
    with log_path.open('w', encoding='utf-8') as log:
        for step in recipe['steps']:
            try:
                argv = [arg.format_map(values) for arg in step['argv']]
            except KeyError as exc:
                raise ToolchainError('unknown recipe substitution') from exc
            if any('\n' in v or '\0' in v for v in argv):
                raise ToolchainError('invalid recipe argument')
            log.write('STEP ' + step['name'] + '\n')
            log.flush()
            cmd = sandbox_command(work, root, argv)
            completed = runner(cmd, stdout=log, stderr=subprocess.STDOUT, check=False, timeout=14400)
            if completed.returncode:
                raise ToolchainError('isolated recipe step failed: ' + stage + '/' + step['name'])
    check_outputs(root, recipe, values)
    return {'stage': stage, 'recipe_sha256': recipe_hash, 'source_lock': lock,
            'log': str(log_path), 'status': 'built-unverified-runtime'}


def inspect_target(root: Path, work: Path, *, runner=subprocess.run) -> dict:
    """Compile, inspect ELF linkage and execute C/C++ via the target loader."""
    gcc = root / 'usr/bin' / (TARGET + '-gcc')
    gxx = root / 'usr/bin' / (TARGET + '-g++')
    assembler = root / 'bin' / (TARGET + '-as')
    linker = root / 'bin' / (TARGET + '-ld')
    loader_guest = '/toolchain/lib64/ld-linux-x86-64.so.2'
    for path in (gcc, gxx, assembler, linker, root / 'lib64/ld-linux-x86-64.so.2'):
        if not path.is_file():
            raise ToolchainError('target tool or loader missing: ' + str(path))
    probe_work = work / 'target-probes'
    probe_work.mkdir()
    (probe_work / 'build').mkdir()
    fixtures = {'c': ('int main(void) {return 0;}\n', '{target}-gcc', 'probe.c'),
                'cxx': ('#include <string>\nint main() {std::string s="ok"; return s.size()!=2;}\n',
                        '{target}-g++', 'probe.cxx')}
    reports = {}
    for kind, (content, compiler, name) in fixtures.items():
        (probe_work / 'build' / name).write_text(content, encoding='utf-8')
        executable = '/work/build/' + kind + '-probe'
        compile_cmd = sandbox_command(probe_work, root,
                      ['/toolchain/usr/bin/' + compiler.format(target=TARGET),
                       '/work/build/' + name, '-o', executable])
        result = runner(compile_cmd, capture_output=True, text=True, timeout=180, check=False)
        if result.returncode:
            raise ToolchainError(kind + ' cross-compile/link failed: ' + result.stderr[-500:])
        read_elf = sandbox_command(probe_work, root, ['/usr/bin/readelf', '-l', executable])
        elf = runner(read_elf, capture_output=True, text=True, timeout=30, check=False)
        if elf.returncode or 'Requesting program interpreter: /lib64/ld-linux-x86-64.so.2' not in elf.stdout:
            raise ToolchainError(kind + ' ELF interpreter does not match target runtime')
        dyn = runner(sandbox_command(probe_work, root, ['/usr/bin/readelf', '-d', executable]),
                     capture_output=True, text=True, timeout=30, check=False)
        if dyn.returncode:
            raise ToolchainError(kind + ' ELF dynamic inspection failed')
        needed = re.findall(r'\(NEEDED\).*?\[([^]]+)\]', dyn.stdout)
        for library in needed:
            if '/' in library or library in ('.', '..'):
                raise ToolchainError('invalid runtime dependency')
            if not any((root / sub / library).is_file() for sub in ('lib64','lib','usr/lib','usr/lib64')):
                raise ToolchainError('target runtime dependency missing: ' + library)
        invoke = sandbox_command(probe_work, root,
                 [loader_guest, '--library-path',
                  '/toolchain/lib64:/toolchain/lib:/toolchain/usr/lib64:/toolchain/usr/lib', executable])
        executed = runner(invoke, capture_output=True, text=True, timeout=60, check=False)
        if executed.returncode:
            raise ToolchainError(kind + ' target runtime execution failed: ' + executed.stderr[-500:])
        reports[kind] = {'needed': needed, 'interpreter': '/lib64/ld-linux-x86-64.so.2',
                         'execution': 'target-loader-success'}
    return {'target': TARGET, 'probes': reports, 'runtime_linkage': 'verified'}


def archive_root(root: Path, destination: Path) -> dict:
    """Export standalone root; digest and member inventory remain external."""
    if destination.exists():
        raise ToolchainError('archive destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    inventory = []
    with tarfile.open(destination, 'w:xz', format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(root.rglob('*')):
            rel = path.relative_to(root)
            if path.is_symlink():
                kind = 'symlink'
            elif path.is_file():
                kind = 'file'
            elif path.is_dir():
                kind = 'directory'
            else:
                raise ToolchainError('unsupported root member type: ' + str(rel))
            inventory.append({'path': rel.as_posix(), 'type': kind})
            tar.add(path, arcname=rel.as_posix(), recursive=False)
    return {'archive': str(destination), 'sha256': file_hash(destination, 'sha256'),
            'entries': inventory}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=1)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--signer-keyring', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.jobs < 1 or args.jobs > 256:
            raise ToolchainError('invalid parallel build count')
        if os.geteuid() == 0:
            raise ToolchainError('run as unprivileged host user')
        baseline = read_json(args.baseline)
        # Verified by source selector before any build. All stages must be mapped.
        for stage in STAGES:
            owner = 'gcc' if stage == 'libstdcxx' else stage
            select_component(baseline, owner)
        workspace = args.workspace.resolve()
        if workspace.exists() and any(workspace.iterdir()):
            raise ToolchainError('new execution needs an empty workspace')
        workspace.mkdir(parents=True, exist_ok=True)
        root = workspace / 'root'
        root.mkdir()
        work = workspace / 'work'
        work.mkdir()
        cache = workspace / 'sources'
        locks = workspace / 'locks'
        evidence = []
        for stage in STAGES:
            evidence.append(run_stage(stage, baseline, cache, locks, root, work,
                                      jobs=args.jobs, offline=args.offline, keyring=args.signer_keyring))
        probe = inspect_target(root, work)
        handoff = archive_root(root, workspace / 'cross-toolchain-root.tar.xz')
        (workspace / 'evidence.json').write_text(json.dumps({'builds': evidence, 'probe': probe,
                                                   'handoff': handoff}, indent=2) + '\n')
        return 0
    except (ToolchainError, SourceError, OSError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
        print('Cross-toolchain blocked: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
