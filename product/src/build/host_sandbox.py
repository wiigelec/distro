"""FS-001 host recipe execution using Bubblewrap.

No recipe is ever run without a successfully started sandbox. This is a
host-write/contamination guard, not a malicious-code security boundary.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Mapping


class SandboxError(RuntimeError):
    """Required isolation could not be established."""


# Host resources are deliberately read-only. Never bind host / wholesale.
HOST_PATHS = ("/usr", "/bin", "/lib", "/lib64", "/etc")
SANDBOX_ROOT = Path("/toolchain")
SANDBOX_WORK = Path("/work")


def _bwrap() -> str:
    executable = shutil.which("bwrap")
    if not executable:
        raise SandboxError("bubblewrap (bwrap) is required; no unrestricted fallback")
    return executable


def _mounts(host_build: Path, host_root: Path) -> list[str]:
    if not host_build.is_dir() or not host_root.is_dir():
        raise SandboxError("build and installation root must exist before sandbox execution")
    if host_build.resolve() == host_root.resolve():
        raise SandboxError("build and installation roots must be distinct")
    # Resolve and pin the configured mounts before construction. Caller owns
    # validating the workspace and rejecting untrusted symlink layouts.
    result = ["--ro-bind", "/usr", "/usr"]
    for path in HOST_PATHS[1:]:
        if Path(path).exists():
            result.extend(("--ro-bind", path, path))
    result.extend(("--bind", str(host_build.resolve()), str(SANDBOX_WORK)))
    result.extend(("--bind", str(host_root.resolve()), str(SANDBOX_ROOT)))
    return result


def recipe_command(
    host_build: Path, host_root: Path, recipe: Path, *,
    source_dir: str, build_dir: str, package: str, version: str,
    step_id: str, target: str = "x86_64-distro-linux-gnu",
) -> list[str]:
    """Construct a fail-closed sandbox invocation for one Bash recipe.

    source_dir/build_dir are sandbox paths under /work, never host paths.
    """
    bwrap = _bwrap()
    recipe = recipe.resolve(strict=True)
    if not recipe.is_file():
        raise SandboxError("recipe must be a regular file")
    for value in (source_dir, build_dir):
        path = Path(value)
        if not path.is_absolute() or path == SANDBOX_WORK or SANDBOX_WORK not in path.parents or ".." in path.parts:
            raise SandboxError("recipe source/build paths must be children of /work")
    if not package or not version or not step_id or not target:
        raise SandboxError("recipe identity and target are required")
    env = {
        "PATH": "/toolchain/tools/bin:/usr/bin:/bin",
        "HOME": "/work", "TMPDIR": "/tmp", "LC_ALL": "C",
        "DISTRO_SOURCE_DIR": source_dir, "DISTRO_BUILD_DIR": build_dir,
        "DISTRO_ROOT_DIR": "/toolchain", "DISTRO_TOOLS_DIR": "/toolchain/tools",
        "DISTRO_PACKAGE_NAME": package, "DISTRO_PACKAGE_VERSION": version,
        "DISTRO_STEP_ID": step_id, "DISTRO_TARGET": target,
    }
    cmd = [bwrap, "--die-with-parent", "--unshare-user", "--unshare-pid",
           "--unshare-net", "--new-session", "--clearenv",
           "--tmpfs", "/tmp", "--tmpfs", "/run", "--proc", "/proc"]
    cmd += _mounts(host_build, host_root)
    cmd += ["--ro-bind", str(recipe), "/recipe.sh"]
    for key, value in env.items():
        cmd += ["--setenv", key, value]
    cmd += ["--chdir", build_dir, "--", "/bin/bash", "/recipe.sh"]
    return cmd


def run_recipe(*args, **kwargs) -> None:
    """Execute one selected Bash recipe; error if isolation or recipe fails."""
    cmd = recipe_command(*args, **kwargs)
    try:
        subprocess.run(cmd, check=True, env={"PATH": os.defpath})
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SandboxError(f"sandboxed recipe did not complete: {exc}") from exc


def probe_bubblewrap() -> None:
    """Verify namespace creation and sandbox mount behavior with an actual run."""
    bwrap = _bwrap()
    cmd = [bwrap, "--die-with-parent", "--unshare-user", "--unshare-pid",
           "--unshare-net", "--clearenv", "--ro-bind", "/usr", "/usr",
           "--tmpfs", "/tmp", "--proc", "/proc",
           "--setenv", "PATH", "/usr/bin", "--", "/usr/bin/sh", "-c",
           "test -d /tmp && test -d /proc && test ! -w /usr"]
    try:
        subprocess.run(cmd, check=True, env={"PATH": os.defpath},
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SandboxError(f"Bubblewrap namespace/mount preflight failed: {exc}") from exc
