"""FS-002 diagnostic: target-root-only ELF interpreter and DT_NEEDED closure.

This is a bounded representative ELF audit, not full-system library coverage.
No ldd or target code runs on the host. Host readelf only inspects bytes; all
filesystem resolution is explicitly confined to the target root.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess


BINARIES = (
    "/usr/bin/bash", "/usr/bin/cat", "/usr/bin/grep", "/usr/bin/sed",
    "/usr/bin/gawk", "/usr/bin/make", "/usr/bin/diff", "/usr/bin/tar",
    "/usr/bin/as", "/usr/bin/ld", "/usr/bin/ar", "/usr/bin/readelf",
    "/usr/bin/gcc", "/usr/bin/g++", "/verify/smoke-c", "/verify/smoke-cpp",
)
# A deterministic, conservative default search contract. Unsupported DT_RPATH
# or DT_RUNPATH forms fail closed rather than guessing glibc search semantics.
DEFAULT_DIRS = ("/lib", "/lib64", "/usr/lib", "/usr/lib64")
INTERP_RE = re.compile(r"Requesting program interpreter:\s*([^\]]+)")
NEEDED_RE = re.compile(r"\(NEEDED\).*Shared library:\s*\[([^\]]+)\]")
PATH_RE = re.compile(r"\((RPATH|RUNPATH)\).*Library (?:rpath|runpath):\s*\[([^\]]*)\]")


class DependencyError(RuntimeError):
    pass


def _target_path(root: Path, absolute: str) -> tuple[Path, str]:
    """Resolve links as the target would; never dereference host absolute links."""
    if not absolute.startswith("/") or "\x00" in absolute:
        raise DependencyError(f"non-absolute target path: {absolute!r}")
    queue = deque(absolute.split('/'))
    resolved: list[str] = []
    links = 0
    while queue:
        part = queue.popleft()
        if part in ('', '.'):
            continue
        if part == '..':
            if not resolved:
                raise DependencyError(f"target path escapes root: {absolute}")
            resolved.pop()
            continue
        probe = root.joinpath(*resolved, part)
        try:
            mode = probe.lstat().st_mode
        except OSError as exc:
            raise DependencyError(f"missing target entry for {absolute}: {probe}") from exc
        if stat.S_ISLNK(mode):
            links += 1
            if links > 40:
                raise DependencyError(f"cyclic target symlink: {absolute}")
            target = os.readlink(probe)
            if target.startswith('/'):
                resolved.clear()
            queue.extendleft(reversed(target.split('/')))
        else:
            resolved.append(part)
    path = root.joinpath(*resolved)
    if not path.is_file() or path.is_symlink():
        raise DependencyError(f"target is not a regular file: {absolute}")
    return path, '/' + '/'.join(resolved)


def _readelf(path: Path) -> dict:
    with path.open('rb') as stream:
        magic = stream.read(4)
    if magic != b'\x7fELF':
        raise DependencyError(f"not an ELF executable/object: {path}")
    result = subprocess.run(['readelf', '-h', '-l', '-d', str(path)],
                            capture_output=True, text=True, timeout=20,
                            env={'PATH': os.defpath, 'LC_ALL': 'C'})
    if result.returncode:
        raise DependencyError(f"readelf rejected {path}: {result.stderr[-500:]}")
    output = result.stdout
    arch_ok = re.search(r'^\s*Machine:\s*Advanced Micro Devices X86-64\s*$', output, re.M)
    if not arch_ok:
        raise DependencyError(f"unexpected ELF architecture: {path}")
    interps = INTERP_RE.findall(output)
    if len(interps) > 1:
        raise DependencyError(f"multiple PT_INTERP segments: {path}")
    search = PATH_RE.findall(output)
    if len(search) > 1 or (search and search[0][0] not in ('RPATH', 'RUNPATH')):
        raise DependencyError(f"ambiguous ELF runtime search path: {path}")
    return {'interpreter': interps[0] if interps else None,
            'needed': NEEDED_RE.findall(output),
            'search_tag': search[0][0] if search else None,
            'search_path': search[0][1] if search else None}


def _search_dirs(identity: str, metadata: dict) -> tuple[str, ...]:
    import posixpath
    search = metadata['search_path']
    if search is None:
        return DEFAULT_DIRS
    if not search:
        raise DependencyError(f"empty ELF runtime search path in {identity}")
    # DT_RPATH inheritance and mixed RPATH/RUNPATH demand a fuller loader
    # emulator; reject RPATH here instead of silently treating it as RUNPATH.
    if metadata['search_tag'] != 'RUNPATH':
        raise DependencyError(f"unsupported DT_RPATH in {identity}")
    result = []
    for item in search.split(':'):
        expanded = item.replace('${ORIGIN}', posixpath.dirname(identity)).replace(
            '$ORIGIN', posixpath.dirname(identity))
        if '$' in expanded or not expanded.startswith('/') or '..' in expanded.split('/'):
            raise DependencyError(f"unsafe/unsupported DT_RUNPATH {item!r} in {identity}")
        result.append(posixpath.normpath(expanded))
    return tuple(result) + DEFAULT_DIRS


def _resolve_needed(root: Path, soname: str, dirs: tuple[str, ...]) -> tuple[Path, str]:
    if not soname or '/' in soname or '\x00' in soname:
        raise DependencyError(f"invalid DT_NEEDED library name: {soname!r}")
    for directory in dirs:
        path = directory.rstrip('/') + '/' + soname
        try:
            return _target_path(root, path)
        except DependencyError:
            continue
    raise DependencyError(f"unresolved DT_NEEDED {soname!r} in {dirs}")


def audit_native_elf(root: Path, scratch: Path, report: Path) -> dict:
    """Audit representative executables, generated C/C++, and transitive libs.

    /verify references scratch; every other path resolves inside target root.
    The diagnostic JSON is written even when missing dependencies are found.
    """
    root = Path(root).absolute()
    scratch = Path(scratch).absolute()
    if root.is_symlink() or not root.is_dir() or scratch.is_symlink() or not scratch.is_dir():
        raise DependencyError('ELF audit requires real isolated root and scratch directories')
    graph: dict[str, dict] = {}
    errors: list[str] = []
    todo = deque(BINARIES)
    while todo:
        identity = todo.popleft()
        if identity in graph:
            continue
        try:
            if identity.startswith('/verify/'):
                path = scratch / identity.removeprefix('/verify/')
                if path.is_symlink() or not path.is_file():
                    raise DependencyError(f'missing generated ELF: {identity}')
                canonical = identity
            else:
                path, canonical = _target_path(root, identity)
            meta = _readelf(path)
            interpreter = meta['interpreter']
            if interpreter is not None:
                _, interpreter_resolved = _target_path(root, interpreter)
                todo.append(interpreter_resolved)
            else:
                interpreter_resolved = None
            directories = _search_dirs(canonical, meta)
            library_map = {}
            for needed in meta['needed']:
                _, library_path = _resolve_needed(root, needed, directories)
                library_map[needed] = library_path
                todo.append(library_path)
            graph[identity] = {
                'canonical_path': canonical,
                'interpreter': interpreter,
                'interpreter_resolved': interpreter_resolved,
                'needed_resolutions': dict(sorted(library_map.items())),
                'search_tag': meta['search_tag'], 'search_path': meta['search_path'],
            }
        except (DependencyError, OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f'{identity}: {exc}')
    stable = json.dumps(graph, sort_keys=True, separators=(',', ':')).encode()
    result = {
        'schema_version': 1, 'step_id': 'native-gcc',
        'state': 'diagnostic-representative-elf-dependency-audit',
        'scope': list(BINARIES),
        'host_userspace_mounted': False,
        'success': not errors,
        'errors': errors,
        'elf_object_count': len(graph),
        'dependency_graph_sha256': hashlib.sha256(stable).hexdigest(),
        'objects': dict(sorted(graph.items())),
    }
    with Path(report).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return result
