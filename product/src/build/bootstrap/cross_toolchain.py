"""Cross-toolchain Bootstrap orchestration; artifact publication is not implemented."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import sys
import tempfile

from build.host_sandbox import probe_bubblewrap, run_recipe
from build.host_requirements import qualify_host
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


def run_stage(root: Path):
    """Construct selected sources in a sandbox; no successful handoff claim."""
    if sys.platform != "linux":
        raise RuntimeError("Cross-toolchain construction requires a Linux host")
    manifests, steps = selected_steps()
    # Qualify host binaries before probing sandbox or altering workspace.
    qualify_host()
    probe_bubblewrap()
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
    for step in steps:
        source_dir, construction_dir = prepare_step(step, manifests[step.name], build, cache)
        run_recipe(build, installed, step.recipe,
                   source_dir="/work/" + str(source_dir.relative_to(build)),
                   build_dir="/work/" + str(construction_dir.relative_to(build)),
                   package=step.name, version=step.version, step_id=step.id,
                   target=TARGET)
    # Separate functional checks and transactional artifact publication are mandatory
    # before this can become the successful cross-toolchain CLI operation.
    raise NotImplementedError("Cross-toolchain archive/relocation acceptance gate not implemented")
