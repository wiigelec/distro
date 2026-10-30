"""Native FS-001 product requirement evaluation (not a regression suite)."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD_SRC = ROOT / "product" / "src"


def _run_selection():
    code = r'''from build.bootstrap.cross_toolchain import selected_steps
manifests, steps = selected_steps()
expected = (
    ("binutils-pass1", "binutils", "2.47"),
    ("gcc-pass1", "gcc", "16.2.0"),
    ("linux-headers", "linux", "7.1.8"),
    ("glibc", "glibc", "2.44"),
    ("gcc-libstdcpp", "gcc", "16.2.0"),
)
actual = tuple((s.id, s.name, s.version) for s in steps)
assert actual == expected, (actual, expected)
assert len({s.id for s in steps}) == len(steps)
assert all(s.name in manifests and s.recipe.is_file() and
           s.recipe.suffix == ".sh" and len(s.checksum) == 64 and
           s.checksum == s.checksum.lower() for s in steps)
assert set(steps[1].supplements) == {"gmp", "mpfr", "mpc"}
assert not steps[4].supplements
assert steps[1].recipe != steps[4].recipe
assert steps[1].checksum == steps[4].checksum
'''
    env = {"PATH": os.defpath, "PYTHONPATH": str(BUILD_SRC), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-B", "-c", code],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def selection_contract() -> bool:
    """Evaluate authoritative manifest/list/recipe resolution and exact ordering."""
    result = _run_selection()
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr)
        return False
    return True


def entrypoint_contract() -> bool:
    """Evaluate the documented CLI's command contract without constructing tools."""
    env = {"PATH": os.defpath, "PYTHONPATH": str(BUILD_SRC), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-B", "-m", "build.cli", "cross-toolchain", "--help"]
    result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode or "--root" not in result.stdout or "--check-host" not in result.stdout:
        print(result.stderr or result.stdout, file=sys.stderr)
        return False
    # The real build path must go through the shared Build construction entrypoint.
    cli = (BUILD_SRC / "build" / "cli.py").read_text(encoding="utf-8")
    return "run_stage(args.root)" in cli and "selected_steps()" in cli


def handoff_contract() -> bool:
    "Exercise archive and metadata acceptance/rejection without a toolchain rebuild."
    code = r'''import copy
import io
import json
from pathlib import Path
import tarfile
import tempfile
from build.bootstrap.cross_toolchain import _validate_candidate_archive
from build.bootstrap.cross_toolchain_metadata import (
    ARCHIVE_NAME, METADATA_NAME, sha256_file, validate_handoff,
    validate_published_handoff,
)

with tempfile.TemporaryDirectory(prefix="fs001-handoff-gate-") as tmp:
    folder = Path(tmp)
    archive = folder / ARCHIVE_NAME
    with tarfile.open(archive, "w:xz", format=tarfile.PAX_FORMAT) as t:
        directory = tarfile.TarInfo("./usr")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        t.addfile(directory)
        data = b"synthetic target payload"
        regular = tarfile.TarInfo("./usr/example")
        regular.size = len(data)
        regular.mode = 0o755
        t.addfile(regular, io.BytesIO(data))
        link = tarfile.TarInfo("./usr/example-link")
        link.type = tarfile.SYMTYPE
        link.linkname = "example"
        t.addfile(link)
    _validate_candidate_archive(archive)
    metadata = {
        "schema_version": 1,
        "artifact": {"type": "cross-toolchain", "stage": "1A",
                     "filename": ARCHIVE_NAME, "format": "tar.xz",
                     "sha256": sha256_file(archive), "size_bytes": archive.stat().st_size},
        "toolchain": {"target": "x86_64-distro-linux-gnu",
                      "sysroot": "/toolchain", "tools_prefix": "/toolchain/tools"},
        "sources": [{"step": "synthetic"}],
        "verification": {"functional": "passed", "relocation": "passed"},
    }
    validate_handoff(archive, metadata)
    (folder / METADATA_NAME).write_text(json.dumps(metadata), encoding="utf-8")
    assert validate_published_handoff(folder) == metadata
    def rejected(m):
        try:
            validate_handoff(archive, m)
        except ValueError:
            return True
        return False
    broken = copy.deepcopy(metadata)
    broken["artifact"]["sha256"] = "0" * 64
    assert rejected(broken), "corrupted digest accepted"
    broken = copy.deepcopy(metadata)
    broken["artifact"]["size_bytes"] += 1
    assert rejected(broken), "wrong size accepted"
    broken = copy.deepcopy(metadata)
    broken["verification"]["relocation"] = "failed"
    assert rejected(broken), "incomplete verification accepted"
    (folder / METADATA_NAME).unlink()
    try:
        validate_published_handoff(folder)
    except ValueError:
        pass
    else:
        raise AssertionError("missing metadata completion marker accepted")
    with tarfile.open(archive, "w:xz", format=tarfile.PAX_FORMAT) as t:
        a = tarfile.TarInfo("./unsafe")
        a.type = tarfile.SYMTYPE
        a.linkname = "/etc"
        t.addfile(a)
        b = tarfile.TarInfo("./unsafe/escape")
        b.size = 1
        t.addfile(b, io.BytesIO(b"x"))
    try:
        _validate_candidate_archive(archive)
    except RuntimeError:
        pass
    else:
        raise AssertionError("archive containing child beneath symlink accepted")
'''
    env = {"PATH": os.defpath, "PYTHONPATH": str(BUILD_SRC), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                            env=env, capture_output=True, text=True)
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr)
        return False
    return True
