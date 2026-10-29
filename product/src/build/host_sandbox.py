"""Sandboxed execution of host-based Build recipes (not a hostile-code boundary)."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


class SandboxError(RuntimeError):
    """Host isolation cannot be established or sandboxed recipe failed."""


HOST_PATHS = ("/usr", "/bin", "/lib", "/lib64", "/etc")
WORK = Path("/work")
TARGET_ROOT = Path("/toolchain")


def _bwrap() -> str:
    exe = shutil.which("bwrap")
    if not exe:
        raise SandboxError("bubblewrap (bwrap) is required; no unrestricted fallback")
    return exe


def _workspace_mounts(host_build: Path, host_root: Path) -> list[str]:
    """Reject symlinked, overlapping and host-system writable mount roots."""
    paths = (Path(host_build), Path(host_root))
    resolved = []
    for path in paths:
        if not path.is_dir() or path.is_symlink():
            raise SandboxError("writable sandbox mount must be an existing real directory")
        canonical = path.resolve(strict=True)
        if canonical != path.absolute():
            raise SandboxError("writable sandbox mount may not traverse symlinked parents")
        if canonical == Path('/') or any(canonical == Path(p) or Path(p) in canonical.parents
                                            for p in ('/usr', '/bin', '/lib', '/lib64', '/etc', '/opt', '/var', '/boot', '/root', '/proc', '/sys', '/dev')):
            raise SandboxError("writable sandbox mount overlaps host system paths")
        resolved.append(canonical)
    first, second = resolved
    if first == second or first in second.parents or second in first.parents:
        raise SandboxError("writable sandbox mounts overlap")
    return ["--bind", str(first), str(WORK), "--bind", str(second), str(TARGET_ROOT)]


def _host_mounts() -> list[str]:
    """Mount qualified host tool locations read-only, keeping symlinks intact."""
    mounts = []
    for item in HOST_PATHS:
        if os.path.lexists(item):
            mounts += ["--ro-bind", item, item]
    return mounts


def _base_command() -> list[str]:
    # bwrap starts with an empty root. The destination directories must exist
    # before any bind, proc, or tmpfs mount is attempted.
    cmd = [_bwrap(), "--die-with-parent", "--unshare-user", "--unshare-pid",
           "--unshare-net", "--new-session", "--clearenv", "--dir", "/tmp",
           "--dir", "/run", "--dir", "/proc", "--dir", "/work",
           "--dir", "/toolchain", "--tmpfs", "/tmp", "--tmpfs", "/run",
           "--proc", "/proc"]
    # Host executables and runtime libraries are read-only.
    cmd += _host_mounts()
    return cmd


def recipe_command(host_build: Path, host_root: Path, recipe: Path, *,
                   source_dir: str, build_dir: str, package: str, version: str,
                   step_id: str, target: str = "x86_64-distro-linux-gnu") -> list[str]:
    cmd = _base_command()
    cmd += _workspace_mounts(host_build, host_root)
    try:
        recipe_path = Path(recipe).resolve(strict=True)
    except OSError as exc:
        raise SandboxError(f"recipe missing: {exc}") from exc
    if not recipe_path.is_file():
        raise SandboxError("recipe must be a regular file")
    for value in (source_dir, build_dir):
        path = Path(value)
        if not path.is_absolute() or path == WORK or WORK not in path.parents or '..' in path.parts:
            raise SandboxError("recipe source/build paths must be children of /work")
    if not (Path(host_build) / Path(source_dir).relative_to(WORK)).is_dir():
        raise SandboxError("recipe source directory is missing")
    if not (Path(host_build) / Path(build_dir).relative_to(WORK)).is_dir():
        raise SandboxError("recipe build directory is missing")
    if not all((package, version, step_id, target)):
        raise SandboxError("recipe identity and target are required")
    # Use an existing read-only directory and retain the recipe's basename;
    # --ro-bind can create the file mount target within that directory.
    cmd += ["--dir", "/recipe", "--ro-bind", str(recipe_path), "/recipe/selected.sh"]
    env = {
        "PATH": "/toolchain/tools/bin:/usr/bin:/bin", "HOME": "/work",
        "TMPDIR": "/tmp", "LC_ALL": "C", "DISTRO_SOURCE_DIR": source_dir,
        "DISTRO_BUILD_DIR": build_dir, "DISTRO_ROOT_DIR": str(TARGET_ROOT),
        "DISTRO_TOOLS_DIR": "/toolchain/tools", "DISTRO_PACKAGE_NAME": package,
        "DISTRO_PACKAGE_VERSION": version, "DISTRO_STEP_ID": step_id,
        "DISTRO_TARGET": target,
    }
    for key, value in env.items():
        cmd += ["--setenv", key, value]
    cmd += ["--chdir", build_dir, "--", "/bin/bash", "/recipe/selected.sh"]
    return cmd


def run_recipe(*args, **kwargs) -> None:
    cmd = recipe_command(*args, **kwargs)
    try:
        subprocess.run(cmd, check=True, env={"PATH": os.defpath})
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SandboxError(f"sandboxed recipe did not complete: {exc}") from exc


def probe_bubblewrap() -> None:
    """Exercise namespaces, mount behavior and read-only host access."""
    exe = shutil.which("bash")
    if not exe or not Path(exe).is_file():
        raise SandboxError("host bash is required")
    cmd = _base_command()
    cmd += ["--setenv", "PATH", "/usr/bin:/bin", "--", exe, "-c",
            "test -d /tmp && test -d /proc && test ! -w /usr && "
            "test ! -e /home && test ! -e /work/unexpected && "
            "test -z \"${DISTRO_PREFLIGHT_SECRET+x}\" && "
            "test -z \"${HOME+x}\" && "
            "test -w /tmp && test ! -w /etc && "
            "! (echo forbidden > /etc/distro-preflight-write-test) 2>/dev/null"]
    try:
        subprocess.run(cmd, check=True,
                       env={"PATH": os.defpath, "DISTRO_PREFLIGHT_SECRET": "not-for-sandbox"},
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SandboxError(f"Bubblewrap namespace/mount preflight failed: {exc}") from exc
