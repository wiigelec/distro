#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import tarfile
import tempfile
import posixpath
from pathlib import Path, PurePosixPath
from typing import Any

IGNORED_TOP_LEVEL = {"dev", "proc", "sys", "run"}
DELETION_MANIFEST = ".__distro_lfs_optimize_deletions__.json"


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


def materialize_delta(
    source_root: Path,
    stage_root: Path,
    changed: list[str],
    after: dict[str, dict[str, Any]],
) -> None:
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True)

    directories = []
    payloads = []
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
        st = src.lstat()
        os.chown(dst, st.st_uid, st.st_gid, follow_symlinks=False)
        shutil.copystat(src, dst, follow_symlinks=False)

    for relative in payloads:
        src = source_root / relative
        dst = stage_root / relative
        dst.parent.mkdir(parents=True, exist_ok=True)

        parent = dst.parent
        while parent != stage_root:
            parent_relative = parent.relative_to(stage_root)
            source_parent = source_root / parent_relative
            st = source_parent.lstat()
            os.chown(parent, st.st_uid, st.st_gid, follow_symlinks=False)
            shutil.copystat(source_parent, parent, follow_symlinks=False)
            parent = parent.parent
        if src.is_symlink():
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            os.symlink(os.readlink(src), dst)
            st = src.lstat()
            os.chown(dst, st.st_uid, st.st_gid, follow_symlinks=False)
        elif src.is_file():
            st = src.lstat()
            hardlink_to = after[relative].get("hardlink_to")
            if hardlink_to is not None:
                target = stage_root / hardlink_to
                if not target.is_file():
                    raise RuntimeError(
                        f"hardlink target not materialized: {relative} -> {hardlink_to}"
                    )
                os.link(target, dst)
            else:
                shutil.copy2(src, dst, follow_symlinks=False)
            os.chown(dst, st.st_uid, st.st_gid, follow_symlinks=False)
            shutil.copystat(src, dst, follow_symlinks=False)
        else:
            raise RuntimeError(f"unsupported changed filesystem object: {relative}")


def create_tar_xz(
    stage_root: Path, artifact: Path, deleted: list[str] | None = None
) -> None:
    artifact.parent.mkdir(parents=True, exist_ok=True)
    deletions = deleted or []
    payload = json.dumps(
        {"schema_version": 1, "deleted": deletions},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    with tarfile.open(artifact, "w:xz") as tar:
        info = tarfile.TarInfo(DELETION_MANIFEST)
        info.size = len(payload)
        info.mode = 0o600
        tar.addfile(info, io.BytesIO(payload))
        for path in sorted(stage_root.rglob("*")):
            relative = path.relative_to(stage_root).as_posix()
            if relative == DELETION_MANIFEST:
                raise RuntimeError(
                    f"artifact payload collides with reserved member: {relative}"
                )
            tar.add(path, arcname=relative, recursive=False)


def _validate_artifact_member(member: tarfile.TarInfo) -> None:
    name = member.name
    normalized = posixpath.normpath(name)
    if name.startswith("/") or normalized == ".." or normalized.startswith("../"):
        raise RuntimeError(f"artifact member escapes target root: {name}")
    if member.issym():
        link = member.linkname
        if link.startswith("/"):
            resolved = posixpath.normpath(link)
        else:
            resolved = posixpath.normpath(
                posixpath.join(posixpath.dirname(name), link)
            )
        if not link.startswith("/") and (
            resolved == ".." or resolved.startswith("../")
        ):
            raise RuntimeError(f"artifact symlink escapes target root: {name} -> {link}")
    if member.islnk():
        link = posixpath.normpath(member.linkname)
        if member.linkname.startswith("/") or link == ".." or link.startswith("../"):
            raise RuntimeError(
                f"artifact hardlink escapes target root: {name} -> {member.linkname}"
            )


def _validate_deleted_path(path: str) -> str:
    normalized = posixpath.normpath(path)
    if (
        not path
        or path.startswith("/")
        or normalized in {".", ".."}
        or normalized.startswith("../")
    ):
        raise RuntimeError(f"artifact deletion escapes target root: {path}")
    return normalized


def _remove_existing_path(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def extract_tar_xz(artifact: Path, target_root: Path) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(artifact, "r:xz") as tar:
        members = tar.getmembers()
        manifests = [member for member in members if member.name == DELETION_MANIFEST]
        if len(manifests) > 1:
            raise RuntimeError("artifact contains multiple deletion manifests")

        deleted: list[str] = []
        if manifests:
            manifest_file = tar.extractfile(manifests[0])
            if manifest_file is None:
                raise RuntimeError("artifact deletion manifest is unreadable")
            manifest = json.load(manifest_file)
            if (
                not isinstance(manifest, dict)
                or manifest.get("schema_version") != 1
                or not isinstance(manifest.get("deleted"), list)
                or not all(isinstance(path, str) for path in manifest["deleted"])
            ):
                raise RuntimeError("artifact deletion manifest is invalid")
            deleted = [_validate_deleted_path(path) for path in manifest["deleted"]]

        payload_members = [
            member for member in members if member.name != DELETION_MANIFEST
        ]
        for member in payload_members:
            _validate_artifact_member(member)

        for relative in sorted(
            set(deleted), key=lambda path: len(PurePosixPath(path).parts), reverse=True
        ):
            target = target_root / relative
            if target.is_symlink() or target.exists():
                _remove_existing_path(target)

        # Artifact members define the final topology. Remove existing
        # non-directory targets first so extraction cannot preserve stale
        # baseline hardlinks when a package replaces one side of a link.
        for member in payload_members:
            target = target_root / member.name
            if member.isdir():
                if target.exists() and not target.is_dir():
                    target.unlink()
                continue
            if target.is_symlink() or target.exists():
                _remove_existing_path(target)

        try:
            tar.extractall(
                target_root,
                members=payload_members,
                numeric_owner=True,
                filter="fully_trusted",
            )
        except TypeError:
            tar.extractall(
                target_root, members=payload_members, numeric_owner=True
            )


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
        (before_root / "usr/bin/remove-me").write_text(
            "remove\n", encoding="utf-8"
        )
        (before_root / "usr/share/remove-tree").mkdir(parents=True)
        (before_root / "usr/share/remove-tree/old").write_text(
            "old\n", encoding="utf-8"
        )
        (before_root / "usr/target/bin").mkdir(parents=True)
        (before_root / "usr/bin/split-link").write_text(
            "baseline\n", encoding="utf-8"
        )
        os.link(
            before_root / "usr/bin/split-link",
            before_root / "usr/target/bin/split-link",
        )
        shutil.copytree(before_root, after_root, dirs_exist_ok=True)
        (after_root / "usr/bin/remove-me").unlink()
        shutil.rmtree(after_root / "usr/share/remove-tree")
        (after_root / "usr/bin/new").write_text("new\n", encoding="utf-8")
        (after_root / "var/cache/private/new").write_text("new\n", encoding="utf-8")
        (after_root / "usr/bin/keep").write_text("changed\n", encoding="utf-8")
        (after_root / "usr/lib").mkdir(parents=True)
        os.symlink("../bin/new", after_root / "usr/lib/new-link")
        os.symlink(
            "/usr/bin/new", after_root / "usr/lib/absolute-new-link"
        )

        # Regression: the baseline may contain a symlink to a directory while
        # the package artifact replaces that path with a real directory.
        (before_root / "usr/lib").mkdir(parents=True, exist_ok=True)
        (before_root / "usr/share/terminfo").mkdir(parents=True)
        os.symlink("../share/terminfo", before_root / "usr/lib/terminfo")
        (after_root / "usr/share/terminfo").mkdir(parents=True, exist_ok=True)
        (after_root / "usr/lib/terminfo").mkdir()
        (after_root / "usr/lib/terminfo/x").write_text("x\n", encoding="utf-8")

        (after_root / "usr/bin/hard-a").write_text("hard\n", encoding="utf-8")
        os.link(after_root / "usr/bin/hard-a", after_root / "usr/bin/hard-b")
        (after_root / "usr/bin/independent-a").write_text(
            "independent-a\n", encoding="utf-8"
        )
        (after_root / "usr/bin/independent-b").write_text(
            "independent-b\n", encoding="utf-8"
        )
        (after_root / "usr/bin/setuid-tool").write_text(
            "setuid\n", encoding="utf-8"
        )
        (after_root / "usr/bin/setuid-tool").chmod(0o4755)

        before = snapshot(before_root)
        after = snapshot(after_root)
        changed, deleted = delta(before, after)
        materialize_delta(after_root, stage, changed, after)

        artifact = base / "proof.tar.xz"
        create_tar_xz(stage, artifact, deleted)
        shutil.copytree(before_root, realized, symlinks=True)
        extract_tar_xz(artifact, realized)

        if snapshot(realized) != after:
            raise RuntimeError("artifact realization self-test mismatch")
