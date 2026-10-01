#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tarfile
import tempfile
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
    if path.is_symlink():
        return {"type": "symlink", "mode": mode, "target": os.readlink(path)}
    if path.is_dir():
        return {"type": "directory", "mode": mode}
    if path.is_file():
        return {
            "type": "file",
            "mode": mode,
            "size": st.st_size,
            "sha256": sha256_file(path),
        }
    return {"type": "special", "mode": mode, "rdev": st.st_rdev}


def snapshot(root: Path) -> dict[str, dict[str, Any]]:
    root = root.resolve()
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in IGNORED_TOP_LEVEL:
            continue
        if relative.parts[:2] == ("tmp", "distro-lfs-optimize"):
            continue
        result[relative.as_posix()] = _record(path)
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
    return changed, deleted


def materialize_delta(source_root: Path, stage_root: Path,
                      changed: list[str]) -> None:
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
        shutil.copystat(src, dst, follow_symlinks=False)

    for relative in payloads:
        src = source_root / relative
        dst = stage_root / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            os.symlink(os.readlink(src), dst)
        elif src.is_file():
            shutil.copy2(src, dst, follow_symlinks=False)
        else:
            raise RuntimeError(f"unsupported changed filesystem object: {relative}")


def create_tar_xz(stage_root: Path, artifact: Path) -> None:
    artifact.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(artifact, "w:xz") as tar:
        for path in sorted(stage_root.rglob("*")):
            tar.add(path, arcname=path.relative_to(stage_root), recursive=False)


def extract_tar_xz(artifact: Path, target_root: Path) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(artifact, "r:xz") as tar:
        try:
            tar.extractall(target_root, filter="data")
        except TypeError:
            root = target_root.resolve()
            for member in tar.getmembers():
                target = (target_root / member.name).resolve()
                if target != root and root not in target.parents:
                    raise RuntimeError(
                        f"artifact member escapes target root: {member.name}"
                    )
            tar.extractall(target_root)


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="lfs-optimize-artifact-test-") as td:
        base = Path(td)
        before_root = base / "before"
        after_root = base / "after"
        stage = base / "stage"
        realized = base / "realized"
        before_root.mkdir()
        (before_root / "usr/bin").mkdir(parents=True)
        (before_root / "usr/bin/keep").write_text("same\n", encoding="utf-8")
        shutil.copytree(before_root, after_root, dirs_exist_ok=True)
        (after_root / "usr/bin/new").write_text("new\n", encoding="utf-8")
        (after_root / "usr/bin/keep").write_text("changed\n", encoding="utf-8")
        (after_root / "usr/lib").mkdir(parents=True)
        os.symlink("../bin/new", after_root / "usr/lib/new-link")

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
