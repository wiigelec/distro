#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tarfile
import tempfile
import posixpath
from pathlib import Path
from typing import Any

IGNORED_TOP_LEVEL = {"dev", "proc", "sys", "run"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    st = path.lstat()
    mode = stat.S_IMODE(st.st_mode)
    common = {"mode": mode, "uid": st.st_uid, "gid": st.st_gid}
    if path.is_symlink():
        return {"type": "symlink", **common, "target": os.readlink(path)}
    if path.is_dir():
        return {"type": "directory", **common}
    if path.is_file():
        return {
            "type": "file",
            **common,
            "size": st.st_size,
            "sha256": sha256_file(path),
        }
    return {"type": "special", **common, "rdev": st.st_rdev}


def snapshot(root: Path) -> dict[str, dict[str, Any]]:
    root = root.resolve()
    result: dict[str, dict[str, Any]] = {}
    hardlinks: dict[tuple[int, int], str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in IGNORED_TOP_LEVEL:
            continue
        if relative.parts[:2] == ("tmp", "distro-lfs-optimize"):
            continue
        relative_name = relative.as_posix()
        record = _record(path)
        if record["type"] == "file":
            st = path.lstat()
            if st.st_nlink > 1:
                key = (st.st_dev, st.st_ino)
                first = hardlinks.get(key)
                if first is None:
                    hardlinks[key] = relative_name
                else:
                    record["hardlink_to"] = first
        result[relative_name] = record
    return result


def snapshot_digest(value: dict[str, dict[str, Any]]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def delta(before: dict[str, dict[str, Any]],
          after: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    deleted = sorted(set(before) - set(after))
    changed = sorted(
        path for path, record in after.items()
        if path not in before or before[path] != record
    )
    changed_set = set(changed)
    hardlink_groups: dict[str, set[str]] = {}
    for path, record in after.items():
        target = record.get("hardlink_to")
        if target is not None:
            hardlink_groups.setdefault(target, {target}).add(path)
    for group in hardlink_groups.values():
        if group & changed_set:
            changed_set.update(group)
    return sorted(changed_set), deleted


def materialize_delta(source_root: Path, stage_root: Path,
                      changed: list[str]) -> None:
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True)

    directories = []
    payloads = []
    hardlinks: dict[tuple[int, int], str] = {}
    for relative in changed:
        src = source_root / relative
        if src.is_dir() and not src.is_symlink():
            directories.append(relative)
        else:
            payloads.append(relative)

    for relative in sorted(directories, key=lambda p: len(Path(p).parts)):
        src = source_root / relative
        dst = stage_root / relative
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copystat(src, dst, follow_symlinks=False)
        st = src.lstat()
        os.chown(dst, st.st_uid, st.st_gid, follow_symlinks=False)

    for relative in payloads:
        src = source_root / relative
        dst = stage_root / relative
        dst.parent.mkdir(parents=True, exist_ok=True)

        parent = dst.parent
        while parent != stage_root:
            parent_relative = parent.relative_to(stage_root)
            source_parent = source_root / parent_relative
            shutil.copystat(source_parent, parent, follow_symlinks=False)
            st = source_parent.lstat()
            os.chown(parent, st.st_uid, st.st_gid, follow_symlinks=False)
            parent = parent.parent
        if src.is_symlink():
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            os.symlink(os.readlink(src), dst)
            st = src.lstat()
            os.chown(dst, st.st_uid, st.st_gid, follow_symlinks=False)
        elif src.is_file():
            st = src.lstat()
            key = (st.st_dev, st.st_ino) if st.st_nlink > 1 else None
            first = hardlinks.get(key) if key is not None else None
            if first is not None:
                os.link(stage_root / first, dst)
            else:
                shutil.copy2(src, dst, follow_symlinks=False)
                if key is not None:
                    hardlinks[key] = relative
            os.chown(dst, st.st_uid, st.st_gid, follow_symlinks=False)
        else:
            raise RuntimeError(f"unsupported changed filesystem object: {relative}")


def create_tar_xz(stage_root: Path, artifact: Path) -> None:
    artifact.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(artifact, "w:xz") as tar:
        for path in sorted(stage_root.rglob("*")):
            tar.add(path, arcname=path.relative_to(stage_root), recursive=False)


def _validate_artifact_member(member: tarfile.TarInfo) -> None:
    name = member.name
    normalized = posixpath.normpath(name)
    if name.startswith("/") or normalized == ".." or normalized.startswith("../"):
        raise RuntimeError(f"artifact member escapes target root: {name}")
    if member.issym():
        link = member.linkname
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), link))
        if link.startswith("/") or resolved == ".." or resolved.startswith("../"):
            raise RuntimeError(f"artifact symlink escapes target root: {name} -> {link}")
    if member.islnk():
        link = posixpath.normpath(member.linkname)
        if member.linkname.startswith("/") or link == ".." or link.startswith("../"):
            raise RuntimeError(
                f"artifact hardlink escapes target root: {name} -> {member.linkname}"
            )


def extract_tar_xz(artifact: Path, target_root: Path) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(artifact, "r:xz") as tar:
        for member in tar.getmembers():
            _validate_artifact_member(member)
        try:
            tar.extractall(
                target_root, numeric_owner=True, filter="fully_trusted"
            )
        except TypeError:
            tar.extractall(target_root, numeric_owner=True)


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="lfs-optimize-artifact-test-") as td:
        base = Path(td)
        before_root = base / "before"
        after_root = base / "after"
        stage = base / "stage"
        realized = base / "realized"
        before_root.mkdir()
        (before_root / "usr/bin").mkdir(parents=True)
        (before_root / "var/cache/private").mkdir(parents=True)
        (before_root / "var/cache/private").chmod(0o700)
        (before_root / "var/cache/private/keep").write_text("same\n", encoding="utf-8")
        (before_root / "usr/bin/keep").write_text("same\n", encoding="utf-8")
        shutil.copytree(before_root, after_root, dirs_exist_ok=True)
        (after_root / "usr/bin/new").write_text("new\n", encoding="utf-8")
        (after_root / "var/cache/private/new").write_text("new\n", encoding="utf-8")
        (after_root / "usr/bin/keep").write_text("changed\n", encoding="utf-8")
        (after_root / "usr/lib").mkdir(parents=True)
        os.symlink("../bin/new", after_root / "usr/lib/new-link")
        (after_root / "usr/bin/hard-a").write_text("hard\n", encoding="utf-8")
        os.link(after_root / "usr/bin/hard-a", after_root / "usr/bin/hard-b")

        before = snapshot(before_root)
        after = snapshot(after_root)
        changed, deleted = delta(before, after)
        if deleted:
            raise RuntimeError(f"self-test unexpected deletion: {deleted}")
        materialize_delta(after_root, stage, changed)

        artifact = base / "proof.tar.xz"
        create_tar_xz(stage, artifact)
        shutil.copytree(before_root, realized)
        extract_tar_xz(artifact, realized)

        if snapshot(realized) != after:
            raise RuntimeError("artifact realization self-test mismatch")
