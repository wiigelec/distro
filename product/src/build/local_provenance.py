"""Verify Distro-maintained source bytes against a specified immutable Git tree.

Validation never executes any source or recipe. This is a read-only source gate,
not evidence of Build execution or package publication.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import re
import subprocess
from build.selection import SelectionError, Source

_OID = re.compile(r'[0-9a-f]{40}')

def _git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.run(['git', '-C', str(root), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise SelectionError('Git source verification failed') from exc

def verify_local_source(source: Source, root: Path, revision: str) -> dict[str, str]:
    """Require HEAD equals exact commit and each declared path is an unchanged Git blob.

    Working-tree files must be regular, tracked, non-symlinked files, matching
    the selected commit bytes. The returned SHA-256 mapping is evidence only.
    """
    if source.kind != 'local' or source.verification != 'git-tree' or not source.paths:
        raise SelectionError('not a repository-local source selection')
    if not isinstance(revision, str) or not _OID.fullmatch(revision):
        raise SelectionError('source revision must be a full immutable commit OID')
    root = Path(root)
    if root.is_symlink() or not root.is_dir() or root.resolve() != root.absolute():
        raise SelectionError('Git source root must be a real canonical directory')
    head = _git(root, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    if head != revision:
        raise SelectionError('repository HEAD differs from selected source revision')
    evidence = {}
    for rel in source.paths:
        # Defensive validation: Source dataclasses may be constructed directly.
        if (not isinstance(rel, str) or not rel or rel.startswith('./') or
                Path(rel).is_absolute() or '..' in Path(rel).parts or
                Path(rel).as_posix() != rel or '\\' in rel):
            raise SelectionError('unsafe local source path')
        path = root / rel
        if path.is_symlink() or not path.is_file() or path.resolve() != path.absolute():
            raise SelectionError('local source must be a regular non-symlinked file')
        record = _git(root, 'ls-tree', revision, '--', rel).decode().strip().splitlines()
        if len(record) != 1:
            raise SelectionError('local source missing from selected commit')
        try:
            metadata, recorded_path = record[0].split('\t', 1)
            mode, typ, oid = metadata.split(' ')
        except ValueError as exc:
            raise SelectionError('invalid Git tree source record') from exc
        if recorded_path != rel or mode not in ('100644', '100755') or typ != 'blob':
            raise SelectionError('source must be a committed regular file')
        committed = _git(root, 'cat-file', 'blob', oid)
        actual = path.read_bytes()
        if actual != committed:
            raise SelectionError('uncommitted local source content differs from selected revision')
        evidence[rel] = hashlib.sha256(committed).hexdigest()
    return evidence
