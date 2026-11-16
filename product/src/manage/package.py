"""FS-003 Manage package creation and independent verification.

One versioned package format shared by Bootstrap and production Build.
Repository publication and installation are separate future Manage operations.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import tempfile


class PackageError(ValueError):
    """Invalid package selection, staged payload, or artifact."""


_NAME = re.compile(r"[a-z][a-z0-9-]*\Z")
_VERSION = re.compile(r"[0-9][A-Za-z0-9.+_-]*\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ARCH = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def _parse_json(data: bytes) -> dict:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageError("invalid package JSON") from exc
    if not isinstance(value, dict) or _json_bytes(value) != data:
        raise PackageError("noncanonical package JSON")
    return value


def _regular_directory(path: Path, *, empty: bool = False) -> Path:
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_dir() or path.resolve(strict=True) != path:
        raise PackageError("expected a real directory without symlinked parents")
    if empty and any(path.iterdir()):
        raise PackageError("destination must be empty")
    return path


def _identity(selection: dict) -> dict:
    if not isinstance(selection, dict) or set(selection) != {"schema_version", "identity", "relationships"} or selection["schema_version"] != 1:
        raise PackageError("unsupported selection schema")
    identity = selection["identity"]
    if not isinstance(identity, dict) or set(identity) != {"name", "version", "architecture", "revision"}:
        raise PackageError("invalid package identity")
    if (not isinstance(identity["name"], str) or not _NAME.fullmatch(identity["name"]) or
        not isinstance(identity["version"], str) or not _VERSION.fullmatch(identity["version"]) or
        not isinstance(identity["architecture"], str) or not _ARCH.fullmatch(identity["architecture"]) or
        type(identity["revision"]) is not int or identity["revision"] < 1):
        raise PackageError("invalid identity values")
    relationships = selection["relationships"]
    if not isinstance(relationships, list) or any(not isinstance(x, dict) or set(x) != {"name", "version"} or
        not isinstance(x["name"], str) or not _NAME.fullmatch(x["name"]) or
        not isinstance(x["version"], str) or not _VERSION.fullmatch(x["version"]) for x in relationships):
        raise PackageError("invalid selected relationships")
    if len({x["name"] for x in relationships}) != len(relationships) or relationships != sorted(relationships, key=lambda x: x["name"]):
        raise PackageError("relationships must be uniquely named and sorted")
    return identity


def _member(name: str) -> str:
    if not isinstance(name, str) or not name or name.startswith("/") or "\\" in name or "\x00" in name:
        raise PackageError("invalid payload member name")
    parts = name.split("/")
    if any(p in ("", ".", "..") for p in parts) or str(PurePosixPath(name)) != name:
        raise PackageError("noncanonical or escaping payload path")
    return name


def _link(name: str, target: str) -> None:
    """For this initial format allow only relative symlinks resolved within root."""
    if not isinstance(target, str) or not target or target.startswith("/") or "\\" in target or "\x00" in target:
        raise PackageError("unsafe absolute or empty symlink")
    stack = name.split("/")[:-1]
    for part in target.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not stack:
                raise PackageError("symlink escapes target root")
            stack.pop()
        else:
            stack.append(part)


def inventory(payload: Path) -> list[dict]:
    payload = _regular_directory(payload)
    records = []
    stack = [payload]
    while stack:
        base = stack.pop()
        for child in sorted(base.iterdir(), key=lambda p: p.name):
            name = _member(child.relative_to(payload).as_posix())
            meta = child.lstat()
            mode = stat.S_IMODE(meta.st_mode)
            if stat.S_ISDIR(meta.st_mode):
                stack.append(child)
            elif stat.S_ISLNK(meta.st_mode):
                target = os.readlink(child)
                _link(name, target)
                records.append({"path": name, "type": "symlink", "target": target, "mode": mode})
            elif stat.S_ISREG(meta.st_mode):
                digest = hashlib.sha256()
                with child.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(block)
                records.append({"path": name, "type": "file", "size": meta.st_size,
                                "sha256": digest.hexdigest(), "mode": mode})
            else:
                raise PackageError(f"unsupported special payload file: {name}")
    records.sort(key=lambda item: item["path"])
    if not records:
        raise PackageError("initial FS-003 package must contain installed payload")
    kinds = {record["path"]: record["type"] for record in records}
    for name in kinds:
        for i in range(1, len(name.split("/"))):
            ancestor = "/".join(name.split("/")[:i])
            if ancestor in kinds:
                raise PackageError("member has non-directory ancestor")
    return records


def _tarinfo(name: str, mode: int, *, size: int = 0, type_: bytes = tarfile.REGTYPE, linkname: str = "") -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.mode, info.size, info.type, info.linkname = mode, size, type_, linkname
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    return info


def create(package: str, exchange: Path) -> Path:
    exchange = _regular_directory(exchange)
    selection_path = exchange / "selection.json"
    if selection_path.is_symlink() or not selection_path.is_file():
        raise PackageError("Build selection.json is missing")
    selection = _parse_json(selection_path.read_bytes())
    ident = _identity(selection)
    if package != ident["name"]:
        raise PackageError("CLI package differs from selected identity")
    payload = _regular_directory(exchange / "payload")
    entries = inventory(payload)
    basename = f"{ident['name']}-{ident['version']}-{ident['architecture']}-r{ident['revision']}.tar.xz"
    destination = exchange / basename
    if destination.exists() or destination.is_symlink():
        raise PackageError("refusing to replace an existing package candidate")
    metadata = {"schema_version": 1, "identity": ident, "relationships": selection["relationships"], "paths": entries}
    manifest_bytes = _json_bytes(metadata)
    with tempfile.NamedTemporaryFile(dir=exchange, prefix=".package-", suffix=".tar.xz", delete=False) as tmp:
        candidate = Path(tmp.name)
    try:
        with tarfile.open(candidate, "w:xz", format=tarfile.PAX_FORMAT) as tar:
            control = _tarinfo("control/manifest.json", 0o644, size=len(manifest_bytes))
            tar.addfile(control, io.BytesIO(manifest_bytes))
            for entry in entries:
                src = payload / entry["path"]
                arc = "payload/" + entry["path"]
                if entry["type"] == "symlink":
                    if not src.is_symlink() or os.readlink(src) != entry["target"]:
                        raise PackageError("staged symlink changed while packaging")
                    tar.addfile(_tarinfo(arc, entry["mode"], type_=tarfile.SYMTYPE, linkname=entry["target"]))
                else:
                    if src.is_symlink() or not src.is_file():
                        raise PackageError("staged regular file changed type")
                    with src.open("rb") as handle:
                        tar.addfile(_tarinfo(arc, entry["mode"], size=entry["size"]), handle)
        if inventory(payload) != entries:
            raise PackageError("staged filesystem changed during packaging")
        verified = verify(candidate)
        if verified != metadata:
            raise PackageError("candidate metadata differs from selection")
        candidate.replace(destination)
    finally:
        candidate.unlink(missing_ok=True)
    return destination


def verify(archive: Path) -> dict:
    archive = Path(archive).absolute()
    if archive.is_symlink() or not archive.is_file():
        raise PackageError("missing regular package archive")
    try:
        with tarfile.open(archive, "r:xz") as tar:
            members = tar.getmembers()
            if not members or members[0].name != "control/manifest.json" or not members[0].isfile():
                raise PackageError("package must start with control manifest")
            if len(members) != len({m.name for m in members}):
                raise PackageError("duplicate archive members")
            if members[0].size > 8 * 1024 * 1024:
                raise PackageError("oversized control metadata")
            stream = tar.extractfile(members[0])
            if stream is None:
                raise PackageError("missing control bytes")
            metadata = _parse_json(stream.read())
            if set(metadata) != {"schema_version", "identity", "relationships", "paths"}:
                raise PackageError("invalid package metadata fields")
            _identity({"schema_version": metadata["schema_version"], "identity": metadata["identity"], "relationships": metadata["relationships"]})
            entries = metadata["paths"]
            if not isinstance(entries, list) or not entries or entries != sorted(entries, key=lambda x: x.get("path", "") if isinstance(x, dict) else ""):
                raise PackageError("invalid ordered path inventory")
            if len(members) != len(entries) + 1:
                raise PackageError("archive and metadata path count mismatch")
            seen = set()
            for member, record in zip(members[1:], entries):
                if not isinstance(record, dict) or "path" not in record:
                    raise PackageError("invalid ownership record")
                name = _member(record["path"])
                if name in seen or member.name != "payload/" + name:
                    raise PackageError("duplicate or mismatched payload entry")
                seen.add(name)
                if type(record.get("mode")) is not int or not 0 <= record["mode"] <= 0o7777 or member.mode != record["mode"]:
                    raise PackageError("invalid payload mode")
                if record.get("type") == "file":
                    if set(record) != {"path", "type", "mode", "size", "sha256"} or not member.isfile() or member.size != record["size"] or not _DIGEST.fullmatch(str(record["sha256"])):
                        raise PackageError("regular file metadata mismatch")
                    contents = tar.extractfile(member)
                    if contents is None:
                        raise PackageError("regular file content missing")
                    digest = hashlib.sha256()
                    for block in iter(lambda: contents.read(1024 * 1024), b""):
                        digest.update(block)
                    if digest.hexdigest() != record["sha256"]:
                        raise PackageError("package payload checksum mismatch")
                elif record.get("type") == "symlink":
                    if set(record) != {"path", "type", "mode", "target"} or not member.issym() or member.linkname != record["target"]:
                        raise PackageError("symlink metadata mismatch")
                    _link(name, member.linkname)
                else:
                    raise PackageError("unsupported payload member type")
            for name in seen:
                parts = name.split("/")
                for i in range(1, len(parts)):
                    if "/".join(parts[:i]) in seen:
                        raise PackageError("payload path has non-directory ancestor")
            ident = metadata["identity"]
            expected_name = f"{ident['name']}-{ident['version']}-{ident['architecture']}-r{ident['revision']}.tar.xz"
            # Candidate temporary names are permitted before atomic promotion.
            if archive.name != expected_name and not archive.name.startswith(".package-"):
                raise PackageError("package filename differs from embedded identity")
            return metadata
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise PackageError(f"invalid package archive: {exc}") from exc


def restore(archive: Path, destination: Path) -> dict:
    """Safely consume a verified package into a fresh, private filesystem root.

    No tar extraction shortcuts: only individually verified regular members and
    in-root-relative symlinks are materialized; no member can traverse a link.
    """
    metadata = verify(archive)
    destination = _regular_directory(destination, empty=True)
    with tarfile.open(archive, "r:xz") as tar:
        members = {member.name: member for member in tar.getmembers()[1:]}
        # The verified metadata lists only leaves, never directory ownership.
        # Create all required directory ancestors first, without following links.
        directory_names = set()
        for record in metadata["paths"]:
            parts = record["path"].split("/")
            directory_names.update("/".join(parts[:n]) for n in range(1, len(parts)))
        for name in sorted(directory_names, key=lambda value: (value.count("/"), value)):
            folder = destination / name
            if folder.exists() or folder.is_symlink():
                raise PackageError("package restoration target unexpectedly occupied")
            folder.mkdir(mode=0o755)
        for record in metadata["paths"]:
            if record["type"] != "file":
                continue
            member = members["payload/" + record["path"]]
            stream = tar.extractfile(member)
            if stream is None:
                raise PackageError("verified file contents missing during restoration")
            target = destination / record["path"]
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as output:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    output.write(chunk)
                os.fchmod(output.fileno(), record["mode"])
        # Symlinks are installed last. No package path has a non-directory
        # ancestor, so restored symlinks are never traversed during creation.
        for record in metadata["paths"]:
            if record["type"] == "symlink":
                os.symlink(record["target"], destination / record["path"])
    if inventory(destination) != metadata["paths"]:
        raise PackageError("restored package does not match verified inventory")
    return metadata
