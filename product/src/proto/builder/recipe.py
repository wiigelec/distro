"""Prototype recipe synthesis from documentation-first discovery."""

from __future__ import annotations

import copy
import platform
import urllib.parse


METHOD_PREFERENCE = ("cmake", "meson", "autotools", "make", "cargo", "go", "python")


def normalized_architecture():
    machine = platform.machine().lower()
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "arm64": "aarch64",
    }
    return aliases.get(machine, machine)


def choose_method(discovery):
    methods = discovery["build"].get("methods", [])
    by_system = {method["system"]: method for method in methods}

    for system in METHOD_PREFERENCE:
        if system in by_system:
            return copy.deepcopy(by_system[system])

    if methods:
        return copy.deepcopy(methods[0])

    raise ValueError("discovery produced no usable build method")


def github_archive_url(repository_url, ref):
    parsed = urllib.parse.urlparse(repository_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() != "github.com" or len(parts) < 2:
        raise ValueError("prototype source archive generation supports github.com only")

    owner = parts[0]
    repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    encoded_ref = urllib.parse.quote(ref, safe="")
    return f"https://github.com/{owner}/{repo}/archive/refs/tags/{encoded_ref}.tar.gz"


def cmake_execution(discovery_method):
    documented = {
        item["phase"]: item["command"]
        for item in discovery_method.get("commands", [])
        if item["phase"] in {"configure", "build", "install"}
    }

    return {
        "derivation": {
            "source": "documentation+prototype-policy",
            "documented_commands": documented,
            "policy_changes": [
                "use fixed /work source, build, and staging paths",
                "set CMAKE_INSTALL_PREFIX=/usr for package filesystem layout",
                "stage install with DESTDIR=/work/stage",
            ],
        },
        "commands": [
            {
                "phase": "configure",
                "command": "cmake -S /work/src -B /work/build -DCMAKE_INSTALL_PREFIX=/usr",
            },
            {
                "phase": "build",
                "command": "cmake --build /work/build --parallel",
            },
            {
                "phase": "install",
                "command": "DESTDIR=/work/stage cmake --install /work/build",
            },
        ],
    }


def generate_recipe(discovery, dependencies):
    method = choose_method(discovery)
    if method["system"] != "cmake":
        raise ValueError(
            f"end-to-end prototype currently implements cmake execution only; "
            f"selected {method['system']}"
        )

    name = discovery["name"]
    if name != "curl":
        raise ValueError("end-to-end prototype bootstrap policy currently exists only for curl")

    version = discovery["version"]["version"]
    ref = discovery["version"]["ref"]
    execution = cmake_execution(method)

    return {
        "schema_version": 1,
        "prototype": True,
        "identity": {
            "name": name,
            "version": version,
            "architecture": normalized_architecture(),
            "revision": "r1",
        },
        "source": {
            "repository": discovery["url"],
            "ref": ref,
            "archive_url": github_archive_url(discovery["url"], ref),
            "sha256": None,
        },
        "build": {
            "system": method["system"],
            "selection_policy": list(METHOD_PREFERENCE),
            "discovery_source": discovery["build"]["source"],
            "documented_method": method,
            **execution,
        },
        "environment": {
            "backend": "oci",
            "image": "debian:12-slim",
            "dependency_source": dependencies["source"],
            "capabilities": dependencies["capabilities"],
            "resolver": dependencies["resolution"],
            "packages": dependencies["resolution"]["packages"],
        },
        "package": {
            "format": "prototype-distro-tar-gzip",
            "install_prefix": "/usr",
        },
    }
