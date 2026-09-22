#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def load_recipe(path: Path) -> dict:
    recipe = json.loads(path.read_text(encoding="utf-8"))
    if recipe.get("schema_version") != 1:
        raise RuntimeError(f"{path}: unsupported recipe schema")
    return recipe


def source_root(output_root: Path, recipe: dict) -> Path:
    identity = recipe["identity"]
    unpack = (
        output_root
        / "work"
        / f"{identity['name']}-{identity['version']}"
        / "unpack"
    )
    children = [path for path in unpack.iterdir() if path.is_dir()]
    if len(children) != 1:
        raise RuntimeError(
            f"{identity['name']}: expected one extracted source directory in {unpack}"
        )
    return children[0]


def invoking_ids() -> tuple[int, int]:
    if os.geteuid() == 0:
        sudo_uid = os.environ.get("SUDO_UID")
        sudo_gid = os.environ.get("SUDO_GID")
        if sudo_uid is not None and sudo_gid is not None:
            return int(sudo_uid), int(sudo_gid)
    return os.getuid(), os.getgid()


def privileged_argv(*args: str) -> list[str]:
    if os.geteuid() == 0:
        return list(args)
    return ["sudo", *args]


def chown_tree(path: Path, uid: int, gid: int) -> None:
    os.chown(path, uid, gid, follow_symlinks=False)
    for entry in path.rglob("*"):
        os.chown(entry, uid, gid, follow_symlinks=False)


def prepare_chroot_devices(chroot_root: Path) -> None:
    dev = chroot_root / "dev"
    null = dev / "null"
    subprocess.run(privileged_argv("mkdir", "-p", str(dev)), check=True)
    if not null.exists():
        subprocess.run(
            privileged_argv("mknod", "-m", "666", str(null), "c", "1", "3"),
            check=True,
        )


def prepare_chroot_workspace(
    chroot_root: Path,
    src: Path,
    name: str,
    version: str,
) -> tuple[Path, Path, Path, Path]:
    chroot_root = chroot_root.resolve()
    if not (chroot_root / "usr/bin/bash").is_file():
        raise RuntimeError(f"{chroot_root}: G1 root does not contain /usr/bin/bash")

    prepare_chroot_devices(chroot_root)

    relative_work = Path("tmp") / "distro-g2" / f"{name}-{version}"
    host_work = chroot_root / relative_work
    if host_work.exists():
        shutil.rmtree(host_work)

    host_src = host_work / "src"
    host_build = host_work / "build"
    host_stage = host_work / "stage"
    shutil.copytree(src, host_src, symlinks=True)
    host_build.mkdir(parents=True)
    host_stage.mkdir(parents=True)

    if os.geteuid() == 0:
        uid, gid = invoking_ids()
        chown_tree(host_work, uid, gid)

    chroot_work = Path("/") / relative_work
    return (
        host_work,
        chroot_work / "src",
        chroot_work / "build",
        chroot_work / "stage",
    )


def execute_recipe(
    recipe_path: Path,
    output_root: Path,
    jobs: int,
    *,
    chroot_root: Path | None = None,
) -> dict:
    recipe = load_recipe(recipe_path)
    identity = recipe["identity"]
    name = identity["name"]
    version = identity["version"]

    package_work = output_root / "work" / f"{name}-{version}"
    src = source_root(output_root, recipe)
    build = package_work / "build"
    stage = package_work / "stage"
    log = package_work / "build.log"

    if build.exists():
        shutil.rmtree(build)
    if stage.exists():
        shutil.rmtree(stage)
    build.mkdir(parents=True)
    stage.mkdir(parents=True)

    env = os.environ.copy()
    env.update(
        {
            "SRC": str(src.resolve()),
            "BUILD": str(build.resolve()),
            "DESTDIR": str(stage.resolve()),
            "JOBS": str(jobs),
        }
    )

    chroot_workspace = None
    if chroot_root is not None:
        (
            chroot_workspace,
            chroot_src,
            chroot_build,
            chroot_stage,
        ) = prepare_chroot_workspace(chroot_root, src, name, version)

    commands = recipe.get("build", {}).get("commands")
    if not isinstance(commands, list) or not commands:
        raise RuntimeError(f"{name}: recipe has no build commands")

    result = {
        "name": name,
        "version": version,
        "recipe": str(recipe_path),
        "build_log": str(log),
        "build_dir": str(build),
        "stage_dir": str(stage),
        "execution": "g1-chroot" if chroot_root is not None else "g0",
        "commands": [],
    }

    with log.open("w", encoding="utf-8") as handle:
        for index, command in enumerate(commands, start=1):
            print(f"==> {name}: command {index}/{len(commands)}", flush=True)
            handle.write(f"\n$ {command}\n")
            handle.flush()

            if chroot_root is None:
                argv = ["/bin/bash", "-o", "pipefail", "-c", command]
                cwd = package_work
                command_env = env
            else:
                script = "\n".join(
                    [
                        'export PATH="/usr/bin:/bin"',
                        'export HOME="/tmp"',
                        f'export SRC="{chroot_src}"',
                        f'export BUILD="{chroot_build}"',
                        f'export DESTDIR="{chroot_stage}"',
                        f'export JOBS="{jobs}"',
                        command,
                    ]
                )
                uid, gid = invoking_ids()
                argv = privileged_argv(
                    "chroot",
                    f"--userspec={uid}:{gid}",
                    str(chroot_root.resolve()),
                    "/usr/bin/bash",
                    "-o",
                    "pipefail",
                    "-c",
                    script,
                )
                cwd = None
                command_env = None

            completed = subprocess.run(
                argv,
                cwd=cwd,
                env=command_env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            command_result = {
                "index": index,
                "command": command,
                "exit_code": completed.returncode,
            }
            result["commands"].append(command_result)

            if completed.returncode != 0:
                result["status"] = "failed"
                result["failed_command"] = index
                result["exit_code"] = completed.returncode
                return result

    if chroot_root is not None:
        host_stage = chroot_workspace / "stage"
        shutil.rmtree(stage)
        shutil.copytree(host_stage, stage, symlinks=True)

    staged = [
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*")
        if path.is_file() or path.is_symlink()
    ]
    result["status"] = "success"
    result["staged_path_count"] = len(staged)
    result["staged_paths_sample"] = staged[:25]
    return result
