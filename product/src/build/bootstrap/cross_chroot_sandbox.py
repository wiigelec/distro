"""Isolated cross-chroot recipe command with a read-only sysroot and staged DESTDIR.

This adapter reuses the existing Build sandbox recipe command and makes only
bounded mount/environment changes. It does not execute recipes or merge output.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

from build.host_sandbox import SandboxError, _workspace_mounts, recipe_command

INSTALL = "/install"


def staged_recipe_command(host_build: Path, host_root: Path, staging: Path,
                          recipe: Path, *, source_dir: str, build_dir: str,
                          package: str, version: str, step_id: str,
                          target: str = "x86_64-distro-linux-gnu",
                          jobs: int = 1) -> list[str]:
    """Require disjoint roots and redirect recipe installation into /install.

    /toolchain remains the read-only compiler sysroot. /work is writable for
    source/build outputs. /install is the sole writable installation mount.
    The caller is responsible for a fresh empty stage and for safe merge policy.
    """
    host_build, host_root, staging = (Path(p).absolute() for p in
                                      (host_build, host_root, staging))
    # Apply the same system-directory and symlink-parent guards as the
    # established writable sandbox roots, then reject every overlap.
    _workspace_mounts(host_build, host_root)
    _workspace_mounts(host_build, staging)
    _workspace_mounts(host_root, staging)
    if any(staging.iterdir()):
        raise SandboxError("staged installation must be empty before recipe execution")
    cmd = recipe_command(host_build, host_root, recipe,
                         source_dir=source_dir, build_dir=build_dir,
                         package=package, version=version, step_id=step_id,
                         target=target, jobs=jobs)
    # The expected sysroot bind comes from the centrally validated command.
    mount = ["--bind", str(host_root), "/toolchain"]
    positions = [i for i in range(len(cmd) - 2) if cmd[i:i+3] == mount]
    if len(positions) != 1:
        raise SandboxError("unable to identify unique target sysroot bind")
    cmd[positions[0]] = "--ro-bind"
    env_key = ["--setenv", "DISTRO_ROOT_DIR", "/toolchain"]
    positions = [i for i in range(len(cmd) - 2) if cmd[i:i+3] == env_key]
    if len(positions) != 1:
        raise SandboxError("unable to identify unique installation environment")
    cmd[positions[0]+2] = INSTALL
    try:
        command_at = cmd.index("--chdir")
    except ValueError as exc:
        raise SandboxError("sandbox command lacks working-directory boundary") from exc
    cmd[command_at:command_at] = ["--dir", INSTALL, "--bind", str(staging), INSTALL]
    return cmd


def run_staged_recipe(*args, **kwargs) -> None:
    """Run an isolated recipe; never merge stage contents automatically."""
    cmd = staged_recipe_command(*args, **kwargs)
    try:
        subprocess.run(cmd, check=True, env={"PATH": os.defpath})
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SandboxError(f"staged cross-chroot recipe failed: {exc}") from exc
