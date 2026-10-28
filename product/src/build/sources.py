"""Verified archive acquisition and safe extraction for FS-001."""
from __future__ import annotations
import hashlib
from pathlib import Path
import tarfile
from urllib.request import urlopen
from urllib.parse import urlsplit
from .selection import Source, SelectionError


def fetch_verified(source: Source, version: str, destination: Path) -> Path:
    """Download only HTTPS bytes, verify before publication, never accept a stale file."""
    url = source.url.replace('{version}', version)
    if urlsplit(url).scheme != 'https' or not source.sha256 or len(source.sha256) != 64:
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
        if digest.hexdigest() != source.sha256:
            raise SelectionError('source SHA-256 mismatch')
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def extract_verified(archive: Path, destination: Path) -> None:
    """Extract a previously verified archive; forbid links and special entries."""
    if destination.exists():
        raise SelectionError('extraction destination must not already exist')
    with tarfile.open(archive, 'r:*') as tar:
        members = tar.getmembers()
        for member in members:
            name = Path(member.name)
            if name.is_absolute() or not name.parts or '..' in name.parts or not (member.isdir() or member.isfile()):
                raise SelectionError(f'unsafe archive member: {member.name}')
        destination.mkdir(parents=True)
        try:
            tar.extractall(destination, members=members, filter='data')
        except Exception:
            import shutil
            shutil.rmtree(destination)
            raise
