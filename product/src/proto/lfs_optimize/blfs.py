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
COLLECTIONS = HERE / "collections"


def package_set_entry(value: Any) -> dict[str, Any]:
    if isinstance(value, str) and value:
        return {"kind": "package", "name": value, "build": None}
    if isinstance(value, dict):
        if set(value) == {"collection"}:
            name = value.get("collection")
            if isinstance(name, str) and name:
                return {"kind": "collection", "name": name}
        name = value.get("name")
        build = value.get("build")
        if (
            set(value).issubset({"name", "build"})
            and isinstance(name, str)
            and name
            and (build is None or (isinstance(build, str) and build))
        ):
            return {"kind": "package", "name": name, "build": build}
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
    if "installed" in selected:
        package["installed"] = copy.deepcopy(selected["installed"])
    package["build"] = build
    package["build_description"] = selected.get("description")
    return package


def load_collection(name: str) -> dict[str, Any]:
    path = COLLECTIONS / f"{name}.json"
    definition = load_json(path)
    if definition.get("name") != name:
        raise RuntimeError(f"{path}: collection identity mismatch")
    procedure = definition.get("procedure")
    members = definition.get("members")
    if not isinstance(procedure, list) or not procedure:
        raise RuntimeError(f"{name}: collection procedure missing")
    if not isinstance(members, list) or not members:
        raise RuntimeError(f"{name}: collection members missing")
    return definition


def enabled_collection_members(definition: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in definition["members"]:
        if isinstance(raw, str):
            member = {"name": raw, "enabled": True}
        elif isinstance(raw, dict):
            member = copy.deepcopy(raw)
        else:
            raise RuntimeError(f"{definition['name']}: invalid collection member")

        name = member.get("name")
        enabled = member.get("enabled", True)
        if not isinstance(name, str) or not name or not isinstance(enabled, bool):
            raise RuntimeError(f"{definition['name']}: invalid collection member")
        if name in seen:
            raise RuntimeError(f"{definition['name']}: duplicate collection member {name}")
        seen.add(name)
        if enabled:
            result.append(member)
    if not result:
        raise RuntimeError(f"{definition['name']}: collection has no enabled members")
    return result


def resolve_collection_member(
    definition: dict[str, Any],
    member: dict[str, Any],
    versions: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    name = member["name"]
    selected = versions.get(name)
    if not isinstance(selected, dict):
        raise RuntimeError(f"development version missing for collection member: {name}")

    version = selected.get("version")
    source = selected.get("source")
    if not isinstance(version, str) or not version:
        raise RuntimeError(f"invalid version selection: {name}")
    if not isinstance(source, dict) or not source.get("url") or not source.get("md5"):
        raise RuntimeError(f"invalid source selection: {name}")

    procedure = member.get("procedure", definition["procedure"])
    if not isinstance(procedure, list) or not procedure:
        raise RuntimeError(f"{definition['name']}:{name}: missing procedure")

    variables = {"name": name, "version": version}
    resolved = {
        "schema_version": 1,
        "name": name,
        "description": member.get(
            "description",
            f"{name}, member of the {definition['name']} executable collection",
        ),
        "dependencies": copy.deepcopy(
            member.get("dependencies", definition.get("dependencies", {}))
        ),
        "procedure": substitute(copy.deepcopy(procedure), variables),
        "installed": copy.deepcopy(
            member.get(
                "installed",
                {"programs": [], "libraries": [], "directories": []},
            )
        ),
        "version": version,
        "source": copy.deepcopy(source),
        "resources": copy.deepcopy(selected.get("resources", {})),
        "reference_metrics": copy.deepcopy(selected.get("reference_metrics", {})),
        "build": f"collection:{definition['name']}",
        "collection": definition["name"],
        "collection_member_index": index,
    }
    return resolved


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
    packages: list[dict[str, Any]] = []
    resolved_names: list[str] = []
    collections: list[dict[str, Any]] = []

    for entry in entries:
        if entry["kind"] == "package":
            name = entry["name"]
            packages.append(
                apply_build(resolve_package(name, versions), entry.get("build"))
            )
            resolved_names.append(name)
            continue

        definition = load_collection(entry["name"])
        members = enabled_collection_members(definition)
        member_names = [member["name"] for member in members]
        collections.append(
            {
                "name": definition["name"],
                "members": member_names,
                "dependencies": copy.deepcopy(definition.get("dependencies", {})),
            }
        )
        for index, member in enumerate(members):
            packages.append(
                resolve_collection_member(definition, member, versions, index)
            )
            resolved_names.append(member["name"])

    if len(resolved_names) != len(set(resolved_names)):
        raise RuntimeError("BLFS package set expands to duplicate packages")
    if set(resolved_names) != set(versions):
        missing = sorted(set(resolved_names) - set(versions))
        extra = sorted(set(versions) - set(resolved_names))
        details = []
        if missing:
            details.append("missing versions: " + ", ".join(missing))
        if extra:
            details.append("unmanaged versions: " + ", ".join(extra))
        raise RuntimeError(
            "BLFS package set/version manifest mismatch (" + "; ".join(details) + ")"
        )

    return {
        "schema_version": 1,
        "package_set": package_set["name"],
        "version_manifest": versions_doc["name"],
        "basis": versions_doc.get("basis"),
        "collections": collections,
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
        "collections": resolved.get("collections", []),
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
                "collections": resolved.get("collections", []),
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
        "collections": resolved.get("collections", []),
        "initial_root_sha256": initial_digest,
        "final_root_sha256": snapshot_digest(snapshot(system_root)),
        "root": str(system_root),
        "packages": package_results,
        "review_required": any(x.get("review_required") for x in package_results),
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="BLFS package/build/collection proof")
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
