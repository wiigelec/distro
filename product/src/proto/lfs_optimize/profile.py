#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from blfs import plan_blfs, resolve_blfs
from resolve import HERE, load_json

PROFILES = HERE / "profiles"
FORBIDDEN_PROFILE_KEYS = {
    "packages",
    "collections",
    "procedure",
    "dependencies",
    "version",
    "source",
    "resources",
    "build",
}


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def profile_path(name: str) -> Path:
    require(
        isinstance(name, str)
        and name
        and "/" not in name
        and "\\" not in name
        and name not in {".", ".."},
        "invalid profile name",
    )
    return PROFILES / f"{name}.json"


def profile_reference(value: Any, field: str) -> Path:
    require(isinstance(value, str) and value, f"profile missing {field}")
    path = Path(value)
    require(
        not path.is_absolute()
        and ".." not in path.parts
        and path.suffix == ".json",
        f"profile {field} must be a repository-relative JSON path",
    )
    target = (HERE / path).resolve()
    require(
        target.is_relative_to(HERE.resolve()) and target.is_file(),
        f"profile {field} target missing: {value}",
    )
    return target


def load_profile(name: str) -> dict[str, Any]:
    profile = load_json(profile_path(name))
    require(profile.get("name") == name, f"{name}: profile identity mismatch")
    require(
        profile.get("resolver") == "blfs",
        f"{name}: unsupported profile resolver",
    )
    forbidden = sorted(FORBIDDEN_PROFILE_KEYS.intersection(profile))
    require(
        not forbidden,
        f"{name}: profile duplicates authoritative package semantics: "
        + ", ".join(forbidden),
    )
    defaults = profile.get("defaults")
    require(
        isinstance(defaults, dict)
        and set(defaults) == {"run_tests"}
        and isinstance(defaults["run_tests"], bool),
        f"{name}: invalid profile defaults",
    )
    runtime_policy = profile.get("runtime_policy")
    require(
        isinstance(runtime_policy, dict)
        and all(isinstance(key, str) and key for key in runtime_policy)
        and all(isinstance(value, str) and value for value in runtime_policy.values()),
        f"{name}: invalid runtime policy",
    )
    profile_reference(profile.get("versions"), "versions")
    profile_reference(profile.get("package_set"), "package_set")
    return profile


def resolve_profile(name: str) -> dict[str, Any]:
    profile = load_profile(name)
    resolved = resolve_blfs(
        profile_reference(profile["versions"], "versions"),
        profile_reference(profile["package_set"], "package_set"),
    )
    return {
        "schema_version": 1,
        "status": "success",
        "profile": profile["name"],
        "description": profile["description"],
        "resolver": profile["resolver"],
        "defaults": profile["defaults"],
        "runtime_policy": profile["runtime_policy"],
        "package_set": resolved["package_set"],
        "version_manifest": resolved["version_manifest"],
        "basis": resolved.get("basis"),
        "collections": resolved["collections"],
        "packages": [
            {
                "name": package["name"],
                "version": package["version"],
                "build": package.get("build", "default"),
                **(
                    {"collection": package["collection"]}
                    if "collection" in package
                    else {}
                ),
            }
            for package in resolved["packages"]
        ],
    }


def plan_profile(name: str, run_tests: bool | None = None) -> dict[str, Any]:
    profile = load_profile(name)
    selected_tests = (
        profile["defaults"]["run_tests"]
        if run_tests is None
        else run_tests
    )
    plan = plan_blfs(
        selected_tests,
        profile_reference(profile["versions"], "versions"),
        profile_reference(profile["package_set"], "package_set"),
    )
    return {
        "schema_version": 1,
        "status": "success",
        "profile": profile["name"],
        "tests_enabled": selected_tests,
        "runtime_policy": profile["runtime_policy"],
        "package_set": plan["package_set"],
        "version_manifest": plan["version_manifest"],
        "collections": plan["collections"],
        "packages": plan["packages"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="resolve a user-facing system profile through authoritative distro state"
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    if args.plan:
        result = plan_profile(
            args.profile,
            False if args.skip_tests else None,
        )
    else:
        result = resolve_profile(args.profile)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
