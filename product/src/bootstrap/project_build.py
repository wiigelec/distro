"""Construct a cross-toolchain in a reusable bootstrap project directory."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from cross_toolchain import (STAGES, ToolchainError, archive_root, digest,
                             inspect_target, read_json, run_stage, TARGET)
from source_artifacts import select_component, file_hash


def stream_command(argv, *, stdout=None, stderr=None, check=False, timeout=None):
    """Write subprocess output to the terminal and retained package log."""
    if stdout is None:
        return subprocess.run(argv, stdout=stdout, stderr=stderr, check=check, timeout=timeout)
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               bufsize=1, text=True)
    try:
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            stdout.write(line)
            stdout.flush()
        code = process.wait(timeout=timeout)
    except BaseException:
        process.kill()
        process.wait()
        raise
    return subprocess.CompletedProcess(argv, code)


def initialize_root(root: Path) -> None:
    """Keep installed files separate from build state and use merged /usr."""
    if root.is_symlink():
        raise ToolchainError('installed root cannot be a symlink')
    root.mkdir(parents=True, exist_ok=True)
    for directory in ('usr/bin', 'usr/sbin', 'usr/lib', 'usr/lib64', 'usr/include'):
        path = root / directory
        if path.is_symlink():
            raise ToolchainError('unsafe installed root directory: ' + directory)
        path.mkdir(parents=True, exist_ok=True)
    for name, destination in {'bin': 'usr/bin', 'sbin': 'usr/sbin',
                              'lib': 'usr/lib', 'lib64': 'usr/lib64'}.items():
        path = root / name
        if path.is_symlink():
            if os.readlink(path) != destination:
                raise ToolchainError('incompatible installed root link: ' + name)
        elif path.exists():
            raise ToolchainError('merged /usr link conflicts with existing root: ' + name)
        else:
            path.symlink_to(destination)


def source_requirements(baseline: dict) -> None:
    for stage in STAGES:
        name = 'gcc' if stage == 'libstdcxx' else stage
        select_component(baseline, name)


def stamp_digest(baseline: dict, stage: str, recipe_path: Path) -> str:
    raw = (baseline['baseline_sha256'] + '\n' + stage + '\n' + digest(recipe_path)).encode()
    return hashlib.sha256(raw).hexdigest()


def load_stamp(path: Path, expected: str, root: Path, stage: str) -> dict | None:
    if not path.is_file():
        return None
    record = read_json(path)
    if record.get('identity') != expected or record.get('status') != 'complete':
        raise ToolchainError('previous installed package inputs changed: ' + stage)
    for item in record.get('outputs', []):
        target = root / item['path']
        if not target.is_file() or file_hash(target, 'sha256') != item['sha256']:
            raise ToolchainError('previous installed package output changed: ' + stage)
    if not record.get('outputs'):
        raise ToolchainError('package stamp has no outputs: ' + stage)
    return record


def build(project: Path, baseline: dict, *, jobs: int = 1,
          keyring: Path | None = None, offline: bool = False) -> dict:
    project = project.expanduser().resolve()
    if project in (Path('/'), Path.home().resolve()):
        raise ToolchainError('unsafe bootstrap project directory')
    root = project / 'root'
    state = project / '.distro-bootstrap'
    if state.is_symlink():
        raise ToolchainError('build state cannot be a symlink')
    # Validate every required source mapping before changing installed files.
    source_requirements(baseline)
    state.mkdir(parents=True, exist_ok=True)
    baseline_path = state / 'baseline.json'
    encoded = (json.dumps(baseline, indent=2, sort_keys=True) + '\n').encode()
    if baseline_path.exists():
        if baseline_path.read_bytes() != encoded:
            raise ToolchainError('execution baseline differs from the existing project')
    else:
        with baseline_path.open('xb') as stream:
            stream.write(encoded)
    stamps = state / 'stamps' / 'cross-toolchain'
    work = state / 'work' / 'cross-toolchain'
    sources = state / 'sources'
    locks = state / 'locks'
    stamps.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    locks.mkdir(parents=True, exist_ok=True)
    if root.exists() and any(root.iterdir()) and not any(stamps.iterdir()):
        raise ToolchainError('nonempty root without resumable build stamps')
    initialize_root(root)
    records = []
    from cross_toolchain import ROOT as RECIPE_ROOT, read_json, validate_recipe
    for index, stage in enumerate(STAGES, 1):
        recipe = RECIPE_ROOT / 'recipes' / (stage + '.json')
        identity = stamp_digest(baseline, stage, recipe)
        stamp_path = stamps / (stage + '.json')
        prior = load_stamp(stamp_path, identity, root, stage)
        if prior:
            print(f'[{index}/{len(STAGES)}] {stage}: verified existing output', flush=True)
            records.append(prior)
            continue
        print(f'[{index}/{len(STAGES)}] {stage}: constructing', flush=True)
        # Preserve logs from a failed attempt; a retry must start with fresh work.
        stale = work / stage
        if stale.exists():
            attempt = 1
            while (work / f'{stage}.failed-{attempt}').exists():
                attempt += 1
            stale.rename(work / f'{stage}.failed-{attempt}')
        outcome = run_stage(stage, baseline, sources, locks, root, work,
                            jobs=jobs, offline=offline, keyring=keyring, runner=stream_command)
        details = read_json(recipe)
        validate_recipe(details, stage)
        values = {'target': TARGET}
        outputs = []
        for entry in details['required_outputs']:
            relative = Path(entry.format_map(values)).relative_to('/toolchain')
            path = root / relative
            outputs.append({'path': relative.as_posix(), 'sha256': file_hash(path, 'sha256')})
        record = {'schema_version': 1, 'status': 'complete', 'identity': identity,
                  'stage': stage, 'outputs': outputs, 'build': outcome}
        with stamp_path.open('x', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write('\n')
        records.append(record)
    # Run validation even after a complete resume, before publishing a handoff.
    probe_work = state / 'validation'
    probe_work.mkdir(exist_ok=True)
    probe = inspect_target(root, probe_work)
    handoff_path = project / 'artifacts' / 'cross-toolchain-root.tar.xz'
    if handoff_path.exists():
        # The archive is an output of this root, not a reusable name alone.
        import tarfile
        with tarfile.open(handoff_path, 'r:xz') as archive:
            members = archive.getmembers()
            expected = {item.relative_to(root).as_posix(): item for item in root.rglob('*')}
            if len(members) != len(expected) or {m.name for m in members} != set(expected):
                raise ToolchainError('existing handoff inventory differs from current root')
            for member in members:
                current = expected[member.name]
                if member.isfile():
                    content = archive.extractfile(member)
                    if not current.is_file() or content is None or (
                            hashlib.sha256(content.read()).hexdigest()
                            != file_hash(current, 'sha256')):
                        raise ToolchainError('existing handoff file differs: ' + member.name)
                elif member.issym():
                    if not current.is_symlink() or member.linkname != os.readlink(current):
                        raise ToolchainError('existing handoff link differs: ' + member.name)
                elif not member.isdir() or not current.is_dir() or current.is_symlink():
                    raise ToolchainError('existing handoff member type differs: ' + member.name)
        print(f'[export] Verified existing archive: {handoff_path}', flush=True)
        handoff = {'archive': str(handoff_path), 'sha256': file_hash(handoff_path, 'sha256')}
    else:
        print(f'[export] Building archive: {handoff_path}', flush=True)
        handoff = archive_root(root, handoff_path)
        print(f'[export] Archive complete: {handoff_path}', flush=True)
    result = {'schema_version': 1, 'status': 'verified', 'target': TARGET,
              'packages': records, 'probe': probe, 'handoff': handoff}
    report = state / 'cross-toolchain-evidence.json'
    if not report.exists():
        with report.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write('\n')
    return result
