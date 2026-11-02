"""Verified archive acquisition and safe extraction for Build."""
from __future__ import annotations
import hashlib
from pathlib import Path
import tarfile
import re
import shutil
import posixpath
from urllib.request import urlopen
from urllib.parse import urlsplit
from .selection import Source, SelectionError


def fetch_verified(source: Source, version: str, destination: Path, checksum: str) -> Path:
    """Download only HTTPS bytes, verify before publication, never accept a stale file."""
    url = source.url.replace('{version}', version)
    if source.verification != 'sha256' or urlsplit(url).scheme != 'https' or not re.fullmatch(r'[0-9a-fA-F]{64}', checksum):
        raise SelectionError('unverified or non-HTTPS source')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.partial')
    digest = hashlib.sha256()
    try:
        with urlopen(url, timeout=60) as response, temporary.open('wb') as out:
            if urlsplit(response.geturl()).scheme != 'https':
                raise SelectionError('source redirected away from HTTPS')
            while piece := response.read(1024 * 1024):
                digest.update(piece)
                out.write(piece)
        if digest.hexdigest() != checksum.lower():
            raise SelectionError('source SHA-256 mismatch')
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def _safe_tar_members(members: list[tarfile.TarInfo]) -> None:
    """Check names and link destinations without allowing an extraction escape."""
    for member in members:
        name = member.name
        if not name or name.startswith('/') or any(p == '..' for p in name.split('/')):
            raise SelectionError(f'unsafe archive member: {name}')
        if not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
            raise SelectionError(f'unsupported archive member: {name}')
        if member.issym() or member.islnk():
            link = member.linkname
            if not link or link.startswith('/'):
                raise SelectionError(f'unsafe absolute/empty archive link: {name}')
            # POSIX tar hardlink paths refer to the archive root; symlink paths
            # are relative to the entry's parent. Reject lexical escapes.
            origin = posixpath.dirname(name) if member.issym() else ''
            depth = 0
            for component in (origin + '/' + link).split('/'):
                if component in ('', '.'):
                    continue
                depth += -1 if component == '..' else 1
                if depth < 0:
                    raise SelectionError(f'escaping archive link: {name}')


def extract_verified(archive: Path, destination: Path) -> None:
    """Extract verified tar data; preserve safe links and clean partial trees."""
    if destination.exists() or destination.is_symlink():
        raise SelectionError('extraction destination must not already exist')
    with tarfile.open(archive, 'r:*') as tar:
        members = tar.getmembers()
        _safe_tar_members(members)
        destination.mkdir(parents=True)
        try:
            # Python's data filter resolves link chains and rejects special
            # filesystem effects not caught by lexical prechecks.
            tar.extractall(destination, members=members, filter='data')
        except Exception:
            shutil.rmtree(destination)
            raise
