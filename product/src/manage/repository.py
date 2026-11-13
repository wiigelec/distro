"""FS-003 local Manage repository publication, one authoritative index.

The repository index is the only publication authority. Artifact files are
immutable; orphan candidates are nonselectable after an interrupted publish.
No remote transport, installation, or dependency resolution is implied.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from manage.package import PackageError, _identity, _json_bytes, _parse_json, _regular_directory, verify

INDEX = "index.json"
ARTIFACTS = "artifacts"
LOCK = ".publish.lock"


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _sync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _validate_record(record: dict, directory: Path) -> None:
    if not isinstance(record, dict) or set(record) != {"identity", "relationships", "paths", "artifact"}:
        raise PackageError("invalid repository package record")
    _identity({"schema_version": 1, "identity": record["identity"], "relationships": record["relationships"]})
    artifact = record["artifact"]
    if not isinstance(artifact, dict) or set(artifact) != {"filename", "size_bytes", "sha256"}:
        raise PackageError("invalid repository artifact reference")
    name = artifact["filename"]
    ident = record["identity"]
    expected = f"{ident['name']}-{ident['version']}-{ident['architecture']}-r{ident['revision']}.tar.xz"
    if name != expected or type(artifact["size_bytes"]) is not int or artifact["size_bytes"] < 1:
        raise PackageError("invalid repository artifact identity or size")
    digest = artifact["sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise PackageError("invalid repository artifact checksum")
    path = directory / ARTIFACTS / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size != artifact["size_bytes"] or _digest(path) != digest:
        raise PackageError("referenced repository artifact missing or corrupted")
    metadata = verify(path)
    for key in ("identity", "relationships", "paths"):
        if metadata[key] != record[key]:
            raise PackageError("repository record differs from verified artifact")


def verify_repository(repo: Path) -> dict:
    """Re-verify all authoritative selections from repository files alone."""
    repo = _regular_directory(repo)
    index = repo / INDEX
    if index.is_symlink():
        raise PackageError("repository index is a symlink")
    if not index.exists():
        raise PackageError("repository has no authoritative index")
    data = _parse_json(index.read_bytes())
    if set(data) != {"schema_version", "packages"} or data["schema_version"] != 1 or not isinstance(data["packages"], list):
        raise PackageError("invalid repository index schema")
    artifacts = _regular_directory(repo / ARTIFACTS)
    records = data["packages"]
    identities: set[tuple] = set()
    owners: dict[str, tuple] = {}
    for record in records:
        _validate_record(record, repo)
        ident = record["identity"]
        key = (ident['name'], ident['version'], ident['architecture'], ident['revision'])
        if key in identities:
            raise PackageError("duplicate published identity")
        identities.add(key)
        for path in record["paths"]:
            owned = path["path"]
            if owned in owners:
                raise PackageError(f"published path ownership collision: {owned}")
            owners[owned] = key
    if records != sorted(records, key=lambda r: (r['identity']['name'], r['identity']['version'], r['identity']['architecture'], r['identity']['revision'])):
        raise PackageError("repository records are not canonically ordered")
    return data


def publish(package: str, repo: Path, exchange: Path) -> Path:
    """Publish a verified Manage-created artifact through a single-writer index.

    The explicit Build exchange is an FS-003 transport extension to DP-004's
    create/publish operations; it never changes the selected package identity.
    """
    repo = _regular_directory(repo)
    exchange = _regular_directory(exchange)
    if repo == exchange or repo in exchange.parents or exchange in repo.parents:
        raise PackageError("repository and Build exchange must be separate roots")
    selected = exchange / "selection.json"
    if selected.is_symlink() or not selected.is_file():
        raise PackageError("missing Build selection.json")
    selection = _parse_json(selected.read_bytes())
    ident = _identity(selection)
    if package != ident["name"]:
        raise PackageError("publish package differs from selected identity")
    name = f"{ident['name']}-{ident['version']}-{ident['architecture']}-r{ident['revision']}.tar.xz"
    source = exchange / name
    if source.is_symlink() or not source.is_file():
        raise PackageError("verified package artifact is missing from Build exchange")
    metadata = verify(source)
    if metadata['identity'] != ident or metadata['relationships'] != selection['relationships']:
        raise PackageError("artifact identity or relationships differ from Build selection")
    # A lock is exclusive, persistent on interruption, and deliberately
    # requires manual resolution if stale; no unsafe automatic lock takeover.
    try:
        lock_fd = os.open(repo / LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    except FileExistsError as exc:
        raise PackageError("repository publish lock exists; concurrent or interrupted publisher") from exc
    try:
        with os.fdopen(lock_fd, 'w') as f:
            f.write('FS-003 exclusive publisher\n')
            f.flush(); os.fsync(f.fileno())
        index = repo / INDEX
        if index.is_symlink():
            raise PackageError("repository index is a symlink")
        if index.exists():
            data = verify_repository(repo)
        else:
            data = {'schema_version': 1, 'packages': []}
        key = (ident['name'], ident['version'], ident['architecture'], ident['revision'])
        owners = {p['path'] for record in data['packages'] for p in record['paths']}
        if any((r['identity']['name'],r['identity']['version'],r['identity']['architecture'],r['identity']['revision']) == key for r in data['packages']):
            raise PackageError("published identity already exists; use a new packaging revision")
        overlap = owners.intersection(p['path'] for p in metadata['paths'])
        if overlap:
            raise PackageError(f"published path ownership conflict: {sorted(overlap)[0]}")
        if (repo / ARTIFACTS).is_symlink():
            raise PackageError("repository artifacts directory is a symlink")
        (repo / ARTIFACTS).mkdir(exist_ok=True)
        artifacts = _regular_directory(repo / ARTIFACTS)
        target = artifacts / name
        if target.exists() or target.is_symlink():
            raise PackageError("artifact filename already present; refusing replacement")
        # Stage bytes in their final filesystem and verify independently before
        # making the index authoritative. An orphan on failure is not published.
        with tempfile.NamedTemporaryFile(dir=artifacts, prefix='.candidate-', delete=False) as tmp:
            candidate = Path(tmp.name)
        try:
            with source.open('rb') as inp, candidate.open('wb') as out:
                shutil.copyfileobj(inp, out)
                out.flush(); os.fsync(out.fileno())
            if candidate.stat().st_size != source.stat().st_size or _digest(candidate) != _digest(source):
                raise PackageError("candidate copy differs from created package")
            # verify() admits an exact target filename or .package- candidate.
            # A temporary candidate uses a strict .package- prefix during check.
            verification = artifacts / ('.package-' + candidate.name.removeprefix('.'))
            candidate.rename(verification)
            candidate = verification
            if verify(candidate) != metadata:
                raise PackageError("published candidate differs from verified package")
            os.link(candidate, target)
            with target.open('rb') as f:
                os.fsync(f.fileno())
            _sync_dir(artifacts)
        finally:
            candidate.unlink(missing_ok=True)
        record = {'identity': ident, 'relationships': metadata['relationships'], 'paths': metadata['paths'],
                  'artifact': {'filename': name, 'size_bytes': target.stat().st_size, 'sha256': _digest(target)}}
        new_records = sorted(data['packages'] + [record], key=lambda r: (r['identity']['name'],r['identity']['version'],r['identity']['architecture'],r['identity']['revision']))
        updated = {'schema_version': 1, 'packages': new_records}
        with tempfile.NamedTemporaryFile(dir=repo, prefix='.index-', delete=False) as tmp:
            candidate_index = Path(tmp.name)
        try:
            with candidate_index.open('wb') as f:
                f.write(_json_bytes(updated)); f.flush(); os.fsync(f.fileno())
            # All referenced bytes are complete before the index promotion.
            candidate_index.replace(index)
            _sync_dir(repo)
        finally:
            candidate_index.unlink(missing_ok=True)
        return target
    finally:
        (repo / LOCK).unlink(missing_ok=True)
        _sync_dir(repo)
