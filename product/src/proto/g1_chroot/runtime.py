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


def dynamic_paths(dynamic: str, relative: str) -> tuple[list[str], list[str]]:
    origin = "/" + str(Path(relative).parent).replace("\\", "/")
    runpath: list[str] = []
    rpath: list[str] = []

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

    return runpath, rpath


def runtime_search_dirs(
    dynamic: str,
    relative: str,
    inherited_rpath: tuple[str, ...] = (),
) -> list[str]:
    runpath, rpath = dynamic_paths(dynamic, relative)
    direct = runpath if runpath else rpath
    return list(
        dict.fromkeys([*direct, *inherited_rpath, *DEFAULT_LIBRARY_DIRS])
    )


def verify_runtime_closure(
    builds: list[dict],
    provider_records: list[dict] | None = None,
) -> dict:
    providers_by_path: dict[str, set[str]] = {}
    absolute_paths: set[str] = set()
    selected_files: dict[str, dict] = {}
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
                absolute = "/" + relative
                add_provider(package, relative)
                if path.is_file() and not path.is_symlink():
                    dynamic = readelf(path, "-d")
                    program = readelf(path, "-l")
                    if dynamic is not None or program is not None:
                        selected_files[absolute] = {
                            "package": package,
                            "path": path,
                            "relative": relative,
                            "dynamic": dynamic,
                            "program": program,
                        }

    missing = []
    missing_keys: set[tuple] = set()
    dependencies: dict[str, set[str]] = {build["name"]: set() for build in builds}
    visited_contexts: set[tuple[str, tuple[str, ...]]] = set()

    def record_missing(item: dict) -> None:
        key = tuple(sorted((name, str(value)) for name, value in item.items()))
        if key not in missing_keys:
            missing_keys.add(key)
            missing.append(item)

    def resolve_needed(
        package: str,
        needed: str,
        search_dirs: list[str],
    ) -> list[str]:
        matches = []
        providers = set()
        for directory in search_dirs:
            candidate = posixpath.join(directory, needed)
            found = providers_by_path.get(candidate, set())
            if found:
                matches.append(candidate)
                providers.update(found)
        dependencies[package].update(
            provider for provider in providers if provider != package
        )
        return matches

    def walk(absolute: str, inherited_rpath: tuple[str, ...]) -> None:
        context = (absolute, inherited_rpath)
        if context in visited_contexts:
            return
        visited_contexts.add(context)

        info = selected_files[absolute]
        package = info["package"]
        relative = info["relative"]
        dynamic = info["dynamic"]

        next_inherited = inherited_rpath
        if dynamic is not None:
            runpath, rpath = dynamic_paths(dynamic, relative)
            if not runpath and rpath:
                next_inherited = tuple(
                    dict.fromkeys([*rpath, *inherited_rpath])
                )

            search_dirs = runtime_search_dirs(
                dynamic,
                relative,
                inherited_rpath,
            )
            for needed in NEEDED_RE.findall(dynamic):
                matches = resolve_needed(package, needed, search_dirs)
                if not matches:
                    record_missing({
                        "package": package,
                        "path": relative,
                        "needed": needed,
                        "search_dirs": search_dirs,
                    })
                    continue
                for match in matches:
                    if match in selected_files:
                        walk(match, next_inherited)

        program = info["program"]
        if program is not None:
            for interpreter in INTERP_RE.findall(program):
                if interpreter not in absolute_paths:
                    record_missing({
                        "package": package,
                        "path": relative,
                        "interpreter": interpreter,
                    })

    # Executables are natural dependency roots. DT_RPATH from these roots is
    # inherited while resolving descendants; DT_RUNPATH remains direct-only.
    roots = []
    for absolute, info in selected_files.items():
        program = info["program"]
        if program is not None and INTERP_RE.search(program):
            roots.append(absolute)

    for absolute in roots:
        walk(absolute, ())

    # Validate any ELF payload not reachable from an executable as its own
    # root. This keeps orphaned shared objects/plugins strict without treating
    # libraries already reached through an executable as standalone programs.
    reached = {absolute for absolute, _ in visited_contexts}
    for absolute in selected_files:
        if absolute not in reached:
            walk(absolute, ())

    return {
        "status": "success" if not missing else "failed",
        "missing": missing,
        "dependencies": {
            name: sorted(values)
            for name, values in dependencies.items()
        },
    }
