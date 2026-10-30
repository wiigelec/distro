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
