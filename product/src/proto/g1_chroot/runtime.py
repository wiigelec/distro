#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path

NEEDED_RE = re.compile(r"\(NEEDED\).*Shared library: \[([^\]]+)\]")
INTERP_RE = re.compile(r"Requesting program interpreter:\s*([^\]]+)")


def readelf(path: Path, *args: str) -> str | None:
    completed = subprocess.run(
        ["readelf", *args, str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout


def verify_runtime_closure(builds: list[dict]) -> dict:
    by_basename: dict[str, set[str]] = {}
    absolute_paths: set[str] = set()
    files: list[tuple[str, Path, str]] = []

    for build in builds:
        package = build["name"]
        stage = Path(build["stage_dir"])
        for path in stage.rglob("*"):
            if path.is_file() or path.is_symlink():
                relative = path.relative_to(stage).as_posix()
                absolute_paths.add("/" + relative)
                by_basename.setdefault(path.name, set()).add(package)
                if path.is_file() and not path.is_symlink():
                    files.append((package, path, relative))

    missing = []
    dependencies: dict[str, set[str]] = {build["name"]: set() for build in builds}

    for package, path, relative in files:
        dynamic = readelf(path, "-d")
        if dynamic is not None:
            for needed in NEEDED_RE.findall(dynamic):
                providers = by_basename.get(needed, set())
                if not providers:
                    missing.append({
                        "package": package,
                        "path": relative,
                        "needed": needed,
                    })
                else:
                    dependencies[package].update(
                        provider for provider in providers if provider != package
                    )

        program = readelf(path, "-l")
        if program is not None:
            for interpreter in INTERP_RE.findall(program):
                if interpreter not in absolute_paths:
                    missing.append({
                        "package": package,
                        "path": relative,
                        "interpreter": interpreter,
                    })

    return {
        "status": "success" if not missing else "failed",
        "missing": missing,
        "dependencies": {
            name: sorted(values)
            for name, values in dependencies.items()
        },
    }
