#!/usr/bin/env python3
from __future__ import annotations

import posixpath
import re
import subprocess
from pathlib import Path

NEEDED_RE = re.compile(r"\(NEEDED\).*Shared library: \[([^\]]+)\]")
INTERP_RE = re.compile(r"Requesting program interpreter:\s*([^\]]+)")
DYNAMIC_PATH_RE = re.compile(
    r"\((RUNPATH|RPATH)\).*Library (?:runpath|rpath): \[([^\]]*)\]"
)
DEFAULT_LIBRARY_DIRS = ("/lib64", "/usr/lib64")


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


def runtime_search_dirs(dynamic: str, relative: str) -> list[str]:
    origin = "/" + str(Path(relative).parent).replace("\\", "/")
    runpath = None
    rpath = None

    for kind, value in DYNAMIC_PATH_RE.findall(dynamic):
        expanded = [
            posixpath.normpath(
                entry.replace("${ORIGIN}", origin).replace("$ORIGIN", origin)
            )
            for entry in value.split(":")
            if entry
        ]
        if kind == "RUNPATH":
            runpath = expanded
        elif kind == "RPATH":
            rpath = expanded

    search = runpath if runpath is not None else (rpath or [])
    return list(dict.fromkeys([*search, *DEFAULT_LIBRARY_DIRS]))


def verify_runtime_closure(
    builds: list[dict],
    provider_records: list[dict] | None = None,
) -> dict:
    providers_by_path: dict[str, set[str]] = {}
    absolute_paths: set[str] = set()
    files: list[tuple[str, Path, str]] = []
    selected = {build["name"] for build in builds}

    def add_provider(package: str, relative: str) -> None:
        absolute = "/" + relative
        absolute_paths.add(absolute)
        providers_by_path.setdefault(absolute, set()).add(package)

    for record in provider_records or []:
        package = record["identity"]["name"]
        if package in selected:
            continue
        for relative in record.get("owned_paths", []):
            add_provider(package, relative)

    for build in builds:
        package = build["name"]
        stage = Path(build["stage_dir"])
        for path in stage.rglob("*"):
            if path.is_file() or path.is_symlink():
                relative = path.relative_to(stage).as_posix()
                add_provider(package, relative)
                if path.is_file() and not path.is_symlink():
                    files.append((package, path, relative))

    missing = []
    dependencies: dict[str, set[str]] = {build["name"]: set() for build in builds}

    for package, path, relative in files:
        dynamic = readelf(path, "-d")
        if dynamic is not None:
            search_dirs = runtime_search_dirs(dynamic, relative)
            for needed in NEEDED_RE.findall(dynamic):
                providers = set()
                for directory in search_dirs:
                    providers.update(
                        providers_by_path.get(
                            posixpath.join(directory, needed),
                            set(),
                        )
                    )
                if not providers:
                    missing.append({
                        "package": package,
                        "path": relative,
                        "needed": needed,
                        "search_dirs": search_dirs,
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
