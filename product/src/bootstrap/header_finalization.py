"""Finalize target GCC limits after libc installation and verify fortified headers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

from cross_toolchain import TARGET, ToolchainError, sandbox_command
from source_artifacts import file_hash, select_component


def finalize_limits(project: Path, baseline: dict, gcc_stamp: dict) -> dict:
    """Reconcile GCC's freestanding limits with installed libc headers."""
    root = project / 'root'
    _, upstream = select_component(baseline, 'gcc')
    version = upstream['version']
    source = project / '.distro-bootstrap/work/cross-toolchain/gcc/src' / ('gcc-' + version) / 'gcc'
    if not source.is_dir() or source.is_symlink():
        raise ToolchainError('verified GCC source tree unavailable for header finalization')
    parts = [source / item for item in ('limitx.h', 'glimits.h', 'limity.h')]
    if any(not p.is_file() or p.is_symlink() for p in parts):
        raise ToolchainError('GCC header inputs missing or unsafe')
    content = b''.join(p.read_bytes() for p in parts)
    if b'#include_next' not in content:
        raise ToolchainError('target-aware GCC limits header missing include_next')
    rel = 'usr/lib/gcc/' + TARGET + '/' + version + '/include/limits.h'
    installed = root / rel
    if not installed.is_file() or installed.is_symlink():
        raise ToolchainError('installed GCC limits header missing or unsafe')
    entries = [x for x in gcc_stamp['outputs'] if x['path'] == rel]
    if len(entries) > 1:
        raise ToolchainError('duplicate GCC header ownership entry')
    if entries:
        if file_hash(installed, 'sha256') != entries[0]['sha256']:
            raise ToolchainError('previously owned GCC header changed')
    elif installed.read_bytes() not in (parts[1].read_bytes(), content):
        raise ToolchainError('unowned GCC header differs from expected GCC-generated inputs')
    if installed.read_bytes() != content:
        with tempfile.NamedTemporaryFile(dir=installed.parent, prefix='.limits-', delete=False) as f:
            replacement = Path(f.name)
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        try:
            replacement.chmod(installed.stat().st_mode & 0o777)
            os.replace(replacement, installed)
        finally:
            replacement.unlink(missing_ok=True)
        print('[headers] Finalized target GCC limits.h', flush=True)
    else:
        print('[headers] Target GCC limits.h already finalized', flush=True)
    work = project / '.distro-bootstrap/validation/cross-toolchain-headers'
    work.mkdir(parents=True, exist_ok=True)
    (work / 'build').mkdir(exist_ok=True)
    source_file = work / 'build/limits.c'
    source_file.write_text('#include <limits.h>\n#include <wchar.h>\n#if MB_LEN_MAX != 16\n#error unexpected MB_LEN_MAX\n#endif\nint limits_probe(void) { return MB_LEN_MAX; }\n')
    command = ['/toolchain/usr/bin/' + TARGET + '-gcc', '--sysroot=/toolchain',
               '-O2', '-D_FORTIFY_SOURCE=2', '-c', '/work/build/limits.c',
               '-o', '/work/build/limits.o']
    result = subprocess.run(sandbox_command(work, root, command), capture_output=True,
                            text=True, timeout=90, check=False)
    if result.returncode or not (work / 'build/limits.o').is_file():
        raise ToolchainError('target fortified limits-header verification failed: ' + result.stderr[-1200:])
    print('[headers] MB_LEN_MAX and fortified wchar.h: verified', flush=True)
    verified = {'path': rel, 'sha256': file_hash(installed, 'sha256')}
    if entries:
        entries[0].update(verified)
    else:
        gcc_stamp['outputs'].append(verified)
    return {'header': verified, 'fortified_wchar': 'verified', 'mb_len_max': 16}
