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


def execute_recipe(
    recipe_path: Path,
    output_root: Path,
    jobs: int,
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
        "commands": [],
    }

    with log.open("w", encoding="utf-8") as handle:
        for index, command in enumerate(commands, start=1):
            print(f"==> {name}: command {index}/{len(commands)}", flush=True)
            handle.write(f"\n$ {command}\n")
            handle.flush()

            completed = subprocess.run(
                ["/bin/bash", "-o", "pipefail", "-c", command],
                cwd=package_work,
                env=env,
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

    staged = [
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*")
        if path.is_file() or path.is_symlink()
    ]
    result["status"] = "success"
    result["staged_path_count"] = len(staged)
    result["staged_paths_sample"] = staged[:25]
    return result
