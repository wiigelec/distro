"""Cross-toolchain Bootstrap construction and verified artifact handoff."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import os
import subprocess
import tarfile
import time

from build.host_sandbox import probe_bubblewrap, run_recipe
from build.bootstrap.cross_toolchain_metadata import (
    ARCHIVE_NAME, METADATA_NAME, make_metadata, validate_handoff,
    validate_published_handoff,
)
from build.host_requirements import qualify_host
from build.bootstrap.cross_toolchain_verification import verify_cross_toolchain
from build.selection import load_manifests, select_steps, SelectionError
from build.sources import fetch_verified, extract_verified

TARGET = "x86_64-distro-linux-gnu"
STAGE = Path(__file__).resolve().parent / "cross-toolchain"
PACKAGES = Path(__file__).resolve().parents[1] / "packages"


def selected_steps():
    """Stage-specific list and recipes, shared authoritative manifests."""
    manifests = load_manifests(PACKAGES)
    steps = select_steps(STAGE / "lists" / "cross-toolchain.yaml", manifests, STAGE)
    return manifests, steps


def _archive(source, version, checksum, cache: Path):
    """Reuse only matching verified bytes; never trust a cache filename alone."""
    destination = cache / (checksum.lower() + ".tar.xz")
    if destination.is_file():
        digest = hashlib.sha256()
        with destination.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() == checksum.lower():
            return destination
        destination.unlink()
    return fetch_verified(source, version, destination, checksum)


def _extract_single(archive: Path, dest: Path):
    """Extract into a private directory, accepting one upstream top-level tree."""
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix="extract-") as tmp:
        stage = Path(tmp) / "payload"
        extract_verified(archive, stage)
        entries = list(stage.iterdir())
        if len(entries) != 1 or not entries[0].is_dir() or entries[0].is_symlink():
            raise SelectionError("upstream archive must contain one real source directory")
        entries[0].rename(dest)


def prepare_step(step, manifest, build: Path, cache: Path):
    """Fresh source tree and build directory for each selected execution step."""
    step_root = build / "steps" / step.id
    if step_root.exists() or step_root.is_symlink():
        raise SelectionError(f"step workspace already exists: {step.id}")
    step_root.mkdir(parents=True)
    source_dir = step_root / "source"
    construction_dir = step_root / "build"
    archive = _archive(manifest.source, step.version, step.checksum, cache)
    _extract_single(archive, source_dir)
    for identity, (version, checksum) in sorted(step.supplements.items()):
        if identity not in manifest.supplements:
            raise SelectionError(f"undeclared supplement: {identity}")
        supplement = _archive(manifest.supplements[identity], version, checksum, cache)
        _extract_single(supplement, source_dir / identity)
    construction_dir.mkdir()
    return source_dir, construction_dir


def _host_jobs() -> int:
    """Use host CPU affinity-aware nproc, never inherited shell variables."""
    result = subprocess.run(["nproc"], check=True, capture_output=True, text=True,
                            env={"PATH": os.defpath}, timeout=10)
    value = result.stdout.strip()
    if not value.isdecimal() or int(value) < 1:
        raise RuntimeError("nproc returned invalid processor count")
    return int(value)

def _validate_candidate_archive(archive: Path) -> None:
    """Validate a GNU-tar filesystem snapshot before restoring into an empty root.

    Absolute symlink targets are valid *target-runtime* paths; the archive must
    never contain a member below any symlink, so extraction cannot write through
    one into the host. Member names have a single unambiguous GNU tar form.
    """
    import posixpath

    with tarfile.open(archive, "r:xz") as tar:
        members = tar.getmembers()
        if not members:
            raise RuntimeError("empty cross-toolchain archive")
        names = {}
        symlinks = set()
        for member in members:
            raw = member.name
            if raw == ".":
                if not member.isdir():
                    raise RuntimeError("archive root must be a directory")
                continue
            if not raw.startswith("./") or raw.startswith("././"):
                raise RuntimeError(f"noncanonical archive member name: {raw}")
            name = raw[2:].rstrip("/")
            if (not name or name.startswith("/") or
                    any(part in ("", ".", "..") for part in name.split("/")) or
                    posixpath.normpath(name) != name):
                raise RuntimeError(f"unsafe archive member name: {raw}")
            if name in names:
                raise RuntimeError(f"duplicate archive member: {raw}")
            if not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
                raise RuntimeError(f"unsupported filesystem archive member: {raw}")
            names[name] = member
            if member.issym():
                if not member.linkname:
                    raise RuntimeError(f"empty symlink target: {raw}")
                symlinks.add(name)
                # Absolute links are target-root paths, not host extraction paths.
                # No archive member may descend through them (checked below).
                if not member.linkname.startswith("/"):
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), member.linkname))
                    if resolved in ("..",) or resolved.startswith("../"):
                        raise RuntimeError(f"escaping relative symlink: {raw}")
        for name, member in names.items():
            parent = posixpath.dirname(name)
            while parent:
                if parent in symlinks:
                    raise RuntimeError(f"archive member beneath symlink: {name}")
                parent = posixpath.dirname(parent)
            if member.islnk():
                target = member.linkname
                if target.startswith("./"):
                    target = target[2:]
                target = target.rstrip("/")
                if (not target or target.startswith("/") or
                        any(part in ("", ".", "..") for part in target.split("/"))):
                    raise RuntimeError(f"unsafe hardlink target: {name}")
                linked = names.get(target)
                if linked is None or not linked.isfile():
                    raise RuntimeError(f"hardlink target must be an archived regular file: {name}")


def publish_archive(root: Path, installed: Path, *, target: str, steps,
                    host_triplet: str, started: float) -> Path:
    """Publish only a candidate that works after extraction in an isolated workspace."""
    artifacts = root / "artifacts"
    if artifacts.is_symlink():
        raise RuntimeError("artifact directory must not be a symlink")
    artifacts.mkdir(exist_ok=True)
    if not artifacts.is_dir() or artifacts.resolve() != artifacts.absolute():
        raise RuntimeError("artifact directory must be a real directory")
    final = artifacts / ARCHIVE_NAME
    final_metadata = artifacts / METADATA_NAME
    if any(p.exists() or p.is_symlink() for p in (final, final_metadata)):
        raise RuntimeError("refusing to replace an existing handoff archive or metadata")
    with tempfile.TemporaryDirectory(dir=artifacts, prefix="handoff-") as candidate_dir:
        candidate = Path(candidate_dir) / ARCHIVE_NAME
        # POSIX pax format, relative paths, symlinks, hardlinks and modes preserved.
        subprocess.run(["tar", "--format=posix", "-cJf", str(candidate),
                        "-C", str(installed), "."], check=True, env={"PATH": os.defpath})
        _validate_candidate_archive(candidate)
        print("[cross-toolchain] Candidate archive created; verifying relocation", flush=True)
        # This independent host workspace is NOT mounted when the restored toolchain
        # executes. The original build/root filesystem is also NOT mounted.
        with tempfile.TemporaryDirectory(prefix="distro-cross-relocated-") as tmp:
            relocated = Path(tmp)
            scratch = relocated / "build"
            restored = relocated / "root"
            scratch.mkdir()
            restored.mkdir()
            # Validated entries have no symlinked ancestor; restored is fresh.
            # GNU tar creates absolute symlinks without dereferencing them.
            subprocess.run(["tar", "-xJf", str(candidate), "-C", str(restored),
                            "--no-same-owner", "--no-overwrite-dir"],
                           check=True, env={"PATH": os.defpath})
            verify_cross_toolchain(scratch, restored, target=target,
                                   original_workspace=root)
        # Metadata becomes the completion marker after full relocation verification.
        metadata = make_metadata(candidate, steps, target=target,
                                 host_triplet=host_triplet,
                                 duration_seconds=time.monotonic() - started)
        validate_handoff(candidate, metadata)
        candidate_meta = Path(candidate_dir) / METADATA_NAME
        candidate_meta.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8")
        # Metadata last: a lone archive must never be treated as published.
        try:
            candidate.replace(final)
            candidate_meta.replace(final_metadata)
            validate_published_handoff(artifacts)
        except Exception:
            # Neither file may survive a failed handoff publication.
            final_metadata.unlink(missing_ok=True)
            final.unlink(missing_ok=True)
            raise
    print(f"[cross-toolchain] Published {final}", flush=True)
    return final


def run_stage(root: Path):
    """Construct and verify a relocatable Stage 1A archive."""
    if sys.platform != "linux":
        raise RuntimeError("Cross-toolchain construction requires a Linux host")
    started = time.monotonic()
    print("[cross-toolchain] Selecting package definitions", flush=True)
    manifests, steps = selected_steps()
    # Qualify host binaries before probing sandbox or altering workspace.
    print("[cross-toolchain] Host qualification", flush=True)
    qualify_host()
    print("[cross-toolchain] Sandbox preflight", flush=True)
    probe_bubblewrap()
    print("[cross-toolchain] Preflight complete", flush=True)
    jobs = _host_jobs()
    print(f"[cross-toolchain] Parallel compilation: nproc={jobs} (make -j{jobs})", flush=True)
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise SelectionError("workspace must be an existing real directory")
    if root.resolve() != root:
        raise SelectionError("workspace must not contain symlinked parents")
    build, installed = root / "build", root / "root"
    if build.exists() or installed.exists():
        raise SelectionError("a fresh workspace without build/ or root/ is required")
    build.mkdir()
    installed.mkdir()
    cache = build / "sources"
    cache.mkdir()
    total = len(steps)
    for index, step in enumerate(steps, 1):
        step_started = time.monotonic()
        prefix = f"[cross-toolchain] [{index}/{total}] {step.id} ({step.name} {step.version})"
        print(f"{prefix}: Preparing verified sources", flush=True)
        try:
            source_dir, construction_dir = prepare_step(step, manifests[step.name], build, cache)
            print(f"{prefix}: Source ready; Starting recipe", flush=True)
            run_recipe(build, installed, step.recipe,
                   source_dir="/work/" + str(source_dir.relative_to(build)),
                   build_dir="/work/" + str(construction_dir.relative_to(build)),
                   package=step.name, version=step.version, step_id=step.id,
                       target=TARGET, jobs=jobs)
        except Exception as exc:
            print(f"{prefix}: FAILED after {time.monotonic() - step_started:.1f}s: {exc}", flush=True)
            raise RuntimeError(f"{step.id} failed: {exc}") from exc
        print(f"{prefix}: Recipe complete ({time.monotonic() - step_started:.1f}s)", flush=True)
    print("[cross-toolchain] Functional verification", flush=True)
    verify_cross_toolchain(build, installed, target=TARGET)
    print(f"[cross-toolchain] Verification complete ({time.monotonic() - started:.1f}s total)", flush=True)
    print("[cross-toolchain] Archiving and relocation verification", flush=True)
    host_triplet = subprocess.run(["gcc", "-dumpmachine"], check=True,
                                  capture_output=True, text=True,
                                  env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}).stdout.strip()
    published = publish_archive(root, installed, target=TARGET, steps=steps,
                                host_triplet=host_triplet, started=started)
    print(f"[cross-toolchain] Stage 1A complete ({time.monotonic() - started:.1f}s): {published}", flush=True)
    return published
