"""Shared target-native Build recipe execution in a fully target-sourced root.

Unlike FS-001/FS-002 host recipes, this production execution mode exposes no
foreign host userspace. The provider of the root (Bootstrap or Manage) is not
part of this interface. This is not a hostile-code security boundary.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

from build.host_sandbox import SandboxError, _bwrap, _workspace_mounts


def _mountpoint(root: Path, name: str) -> None:
    """Create only empty mounting directories in a private restored root."""
    path = root / name
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise SandboxError(f"invalid native root mountpoint: {name}")
    if not path.exists():
        path.mkdir(mode=0o755)
    if path.resolve(strict=True) != path:
        raise SandboxError(f"native root mountpoint traverses symlinks: {name}")
    if name in {"work", "install"} and any(path.iterdir()):
        raise SandboxError(f"native mountpoint must be empty: {name}")


def native_recipe_command(work: Path, root: Path, stage: Path, recipe: Path, *,
                          source_dir: str, build_dir: str, package: str,
                          version: str, step_id: str, target: str,
                          jobs: int = 1, linux_headers: Path | None = None,
                          native_seed: Path | None = None,
                          native_linker_seed: Path | None = None) -> list[str]:
    """Produce the same target-native execution command for every root provider.

    Root filesystem is mounted read-only at /. /work and /install alone are
    writable Bind mounts. Sources and build paths are children of /work.
    """
    work, root, stage = (Path(p).absolute() for p in (work, root, stage))
    # Reuse Build's established mount-root checks, including overlap and
    # symlink-parent refusal, without inheriting the host userspace mounts.
    _workspace_mounts(work, root)
    _workspace_mounts(work, stage)
    _workspace_mounts(root, stage)
    if any(stage.iterdir()):
        raise SandboxError("native package stage must start empty")
    if not isinstance(jobs, int) or isinstance(jobs, bool) or jobs < 1:
        raise SandboxError("native jobs must be a positive integer")
    if not all(isinstance(v, str) and v for v in (package, version, step_id, target)):
        raise SandboxError("native package identity is incomplete")
    for name in ("dev", "proc", "tmp", "run", "work", "install", "recipe"):
        _mountpoint(root, name)
    for value in (source_dir, build_dir):
        candidate = Path(value)
        if (not candidate.is_absolute() or candidate == Path("/work") or
                Path("/work") not in candidate.parents or ".." in candidate.parts):
            raise SandboxError("native recipe paths must be beneath /work")
        if not (work / candidate.relative_to("/work")).is_dir():
            raise SandboxError(f"native recipe workspace unavailable: {value}")
    if linux_headers is not None:
        linux_headers = Path(linux_headers).absolute()
        if (linux_headers.is_symlink() or not linux_headers.is_dir() or
                linux_headers.resolve(strict=True) != linux_headers):
            raise SandboxError("selected Linux headers must be a real directory")
        if not (linux_headers / "linux").is_dir() or not (linux_headers / "asm-generic").is_dir():
            raise SandboxError("selected Linux headers directories missing")
        for other in (work, root, stage):
            _workspace_mounts(linux_headers, other)
        if package != "glibc":
            raise SandboxError("Linux headers overlay is permitted only for Glibc")
    if native_seed is not None:
        if linux_headers is not None or package != "binutils":
            raise SandboxError("native seed overlay is restricted to Binutils bootstrap")
        native_seed = Path(native_seed).absolute()
        if (native_seed.is_symlink() or not native_seed.is_dir() or
                native_seed.resolve(strict=True) != native_seed):
            raise SandboxError("native seed must be a real directory")
        for other in (work, root, stage):
            _workspace_mounts(native_seed, other)
        if (not (native_seed / "usr/include/linux").is_dir() or
                not (native_seed / "usr/lib").is_dir() or
                not (native_seed / ".distro/installed.json").is_file()):
            raise SandboxError("native seed lacks selected header/library/state layout")
    if native_linker_seed is not None:
        if linux_headers is not None or native_seed is not None or package != 'gcc':
            raise SandboxError('native linker seed overlay is restricted to GCC')
        native_linker_seed = Path(native_linker_seed).absolute()
        if (native_linker_seed.is_symlink() or not native_linker_seed.is_dir() or
                native_linker_seed.resolve(strict=True) != native_linker_seed):
            raise SandboxError('selected native linker seed must be a real directory')
        for other in (work, root, stage):
            _workspace_mounts(native_linker_seed, other)
        required = ('usr/include/linux', 'usr/include/asm-generic',
                    'usr/bin/as', 'usr/bin/ld', 'usr/lib', '.distro/installed.json')
        for rel in required:
            entry = native_linker_seed / rel
            if not entry.exists() or entry.is_symlink():
                raise SandboxError(f'native linker seed path missing or unsafe: {rel}')
    recipe = Path(recipe).resolve(strict=True)
    if not recipe.is_file():
        raise SandboxError("native recipe must be an existing regular file")
    # Explicit namespace and no host userspace bind mounts. Native /bin/bash,
    # make, compiler, dynamic loader, etc., must all come from restored root.
    cmd = [
        _bwrap(), "--die-with-parent", "--unshare-user", "--unshare-pid",
        "--unshare-net", "--new-session", "--clearenv",
        "--ro-bind", str(root), "/", "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/tmp", "--tmpfs", "/run",
        "--bind", str(work), "/work", "--bind", str(stage), "/install",
        # The target root is read-only; a private tmpfs allows bwrap to
        # create the destination of this single-file recipe mount.
        "--tmpfs", "/recipe",
        "--ro-bind", str(recipe), "/recipe/selected.sh",
    ]
    if linux_headers is not None:
        # A private tmpfs provides the bind destination without writing
        # into the authenticated read-only bootstrap root.
        cmd += ["--tmpfs", "/distro-prerequisites",
                "--ro-bind", str(linux_headers), "/distro-prerequisites/include"]
    if native_seed is not None:
        cmd += ["--tmpfs", "/distro-seed",
                "--ro-bind", str(native_seed), "/distro-seed/root"]
    if native_linker_seed is not None:
        cmd += ['--tmpfs', '/distro-linker',
                '--ro-bind', str(native_linker_seed), '/distro-linker/root']
    environment = {
        "PATH": "/usr/bin:/bin", "HOME": "/work", "TMPDIR": "/tmp",
        "LC_ALL": "C", "DISTRO_SOURCE_DIR": source_dir,
        "DISTRO_BUILD_DIR": build_dir, "DISTRO_ROOT_DIR": "/install",
        "DISTRO_PACKAGE_NAME": package, "DISTRO_PACKAGE_VERSION": version,
        "DISTRO_STEP_ID": step_id, "DISTRO_TARGET": target,
        "DISTRO_JOBS": str(jobs),
    }
    if linux_headers is not None:
        environment["DISTRO_LINUX_HEADERS_DIR"] = "/distro-prerequisites/include"
    if native_seed is not None:
        environment["DISTRO_NATIVE_SEED_ROOT"] = "/distro-seed/root"
    if native_linker_seed is not None:
        environment['DISTRO_NATIVE_LINKER_ROOT'] = '/distro-linker/root'
    for key, value in environment.items():
        cmd += ["--setenv", key, value]
    cmd += ["--chdir", build_dir, "--", "/bin/bash", "/recipe/selected.sh"]
    return cmd


def run_native_recipe(*args, **kwargs) -> None:
    cmd = native_recipe_command(*args, **kwargs)
    try:
        subprocess.run(cmd, check=True, env={"PATH": os.defpath})
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SandboxError(f"isolated native recipe failed: {exc}") from exc


def verify_staged_sed(root: Path, stage: Path) -> None:
    """Execute the staged native Sed against the imported target runtime only."""
    root, stage = Path(root).absolute(), Path(stage).absolute()
    _workspace_mounts(root, stage)
    program = stage / "usr/bin/sed"
    if program.is_symlink() or not program.is_file():
        raise SandboxError("staged native Sed binary missing or not a regular file")
    cmd = [
        _bwrap(), "--die-with-parent", "--unshare-user", "--unshare-pid",
        "--unshare-net", "--new-session", "--clearenv",
        "--ro-bind", str(root), "/", "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/tmp", "--tmpfs", "/run",
        "--ro-bind", str(stage), "/install",
        "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LC_ALL", "C",
        "--", "/install/usr/bin/sed", "-e", "s/foo/bar/",
    ]
    try:
        result = subprocess.run(cmd, input=b"foo\n", capture_output=True, check=True,
                                timeout=60, env={"PATH": os.defpath})
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise SandboxError(f"staged Sed failed within target-native runtime: {exc}") from exc
    if result.stdout != b"bar\n":
        raise SandboxError("staged Sed native functional output mismatch")
