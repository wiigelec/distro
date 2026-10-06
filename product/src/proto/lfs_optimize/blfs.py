#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from artifact import snapshot, snapshot_digest
from execute import build_package, clone_root, plan, require_root
from resolve import HERE, load_json, resolve_package, substitute

BUILDS = HERE / "blfs-builds"


def package_set_entry(value: Any) -> tuple[str, str | None]:
    if isinstance(value, str) and value:
        return value, None
    if isinstance(value, dict):
        name = value.get("name")
        build = value.get("build")
        if (
            isinstance(name, str)
            and name
            and (build is None or (isinstance(build, str) and build))
        ):
            return name, build
    raise RuntimeError("invalid BLFS package-set entry")


def apply_build(package: dict[str, Any], build: str | None) -> dict[str, Any]:
    package = copy.deepcopy(package)
    package["build"] = "default"
    if build is None:
        return package

    path = BUILDS / f"{package['name']}-{build}.json"
    definition = load_json(path)
    if definition.get("package") != package["name"] or definition.get("build") != build:
        raise RuntimeError(f"{path}: build identity mismatch")

    selected = substitute(definition, {"version": package["version"]})
    procedure = selected.get("procedure")
    if not isinstance(procedure, list) or not procedure:
        raise RuntimeError(f"{package['name']}[{build}]: missing procedure")

    package["procedure"] = copy.deepcopy(procedure)
    if "dependencies" in selected:
        package["dependencies"] = copy.deepcopy(selected["dependencies"])
    package["build"] = build
    package["build_description"] = selected.get("description")
    return package


def resolve_blfs(
    versions_path: Path | None = None,
    package_set_path: Path | None = None,
) -> dict[str, Any]:
    package_set_path = package_set_path or HERE / "blfs-package-set.json"
    versions_path = versions_path or HERE / "versions" / "blfs-development.json"
    package_set = load_json(package_set_path)
    versions_doc = load_json(versions_path)
    versions = versions_doc.get("packages")
    raw_entries = package_set.get("packages")

    if not isinstance(versions, dict):
        raise RuntimeError("BLFS version manifest packages must be an object")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise RuntimeError("BLFS package set must contain packages")

    entries = [package_set_entry(entry) for entry in raw_entries]
    names = [name for name, _ in entries]
    if len(names) != len(set(names)):
        raise RuntimeError("BLFS package set contains duplicate packages")
    if set(names) != set(versions):
        raise RuntimeError("BLFS package set/version manifest mismatch")

    packages = [
        apply_build(resolve_package(name, versions), build)
        for name, build in entries
    ]
    return {
        "schema_version": 1,
        "package_set": package_set["name"],
        "version_manifest": versions_doc["name"],
        "basis": versions_doc.get("basis"),
        "packages": packages,
    }


def plan_blfs(
    run_tests: bool,
    versions_path: Path | None = None,
    package_set_path: Path | None = None,
) -> dict[str, Any]:
    resolved = resolve_blfs(versions_path, package_set_path)
    return {
        "schema_version": 1,
        "status": "success",
        "mode": "plan",
        "package_set": resolved["package_set"],
        "version_manifest": resolved["version_manifest"],
        "packages": [plan(package, run_tests) for package in resolved["packages"]],
    }


def build_blfs(
    root: Path,
    work: Path,
    cache: Path,
    run_tests: bool,
    versions_path: Path | None = None,
    package_set_path: Path | None = None,
) -> dict[str, Any]:
    require_root()
    root = root.resolve()
    if not (root / "usr/bin/bash").is_file():
        raise RuntimeError(f"{root}: execution root lacks /usr/bin/bash")

    resolved = resolve_blfs(versions_path, package_set_path)
    system_root = work / "blfs" / "root"
    package_work = work / "blfs" / "packages"
    result_path = work / "blfs" / "result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)

    clone_root(root, system_root)
    initial_digest = snapshot_digest(snapshot(system_root))
    package_results: list[dict[str, Any]] = []

    for package in resolved["packages"]:
        result = build_package(
            package, system_root, package_work, cache, run_tests, system_root
        )
        package_results.append(result)
        if result["status"] != "success":
            payload = {
                "schema_version": 1,
                "status": "failure",
                "package_set": resolved["package_set"],
                "version_manifest": resolved["version_manifest"],
                "initial_root_sha256": initial_digest,
                "failed_package": package["name"],
                "packages": package_results,
            }
            result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            return payload

    payload = {
        "schema_version": 1,
        "status": "success",
        "package_set": resolved["package_set"],
        "version_manifest": resolved["version_manifest"],
        "initial_root_sha256": initial_digest,
        "final_root_sha256": snapshot_digest(snapshot(system_root)),
        "root": str(system_root),
        "packages": package_results,
        "review_required": any(x.get("review_required") for x in package_results),
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="M8 BLFS package/build proof")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/lfs-optimize-m8"))
    parser.add_argument("--cache", type=Path, default=Path("/tmp/lfs-optimize-cache"))
    parser.add_argument(
        "--versions", type=Path, default=HERE / "versions" / "blfs-development.json"
    )
    parser.add_argument(
        "--package-set", type=Path, default=HERE / "blfs-package-set.json"
    )
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()

    run_tests = not args.skip_tests
    if args.plan:
        result = plan_blfs(run_tests, args.versions, args.package_set)
    else:
        if args.root is None:
            parser.error("--root is required unless --plan is used")
        result = build_blfs(
            args.root, args.work, args.cache, run_tests, args.versions, args.package_set
        )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
