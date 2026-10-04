#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from artifact import snapshot, snapshot_digest
from execute import build_package, clone_root, plan, require_root
from resolve import HERE, resolve


def plan_system(run_tests: bool, versions_path: Path | None = None,
                package_set_path: Path | None = None) -> dict[str, Any]:
    resolved = resolve(versions_path=versions_path, package_set_path=package_set_path)
    packages = resolved["packages"]
    return {
        "schema_version": 1,
        "status": "success",
        "mode": "plan",
        "package_set": resolved["package_set"],
        "version_manifest": resolved["version_manifest"],
        "packages": [plan(package, run_tests) for package in packages],
    }


def build_system(root: Path, work: Path, cache: Path,
                 run_tests: bool, versions_path: Path | None = None,
                 package_set_path: Path | None = None) -> dict[str, Any]:
    require_root()
    root = root.resolve()
    if not (root / "usr/bin/bash").is_file():
        raise RuntimeError(f"{root}: execution root lacks /usr/bin/bash")

    resolved = resolve(versions_path=versions_path, package_set_path=package_set_path)
    system_work = work / "system"
    system_root = system_work / "root"
    package_work = work / "packages"
    result_path = system_work / "result.json"
    system_work.mkdir(parents=True, exist_ok=True)

    clone_root(root, system_root)
    initial_digest = snapshot_digest(snapshot(system_root))
    package_results: list[dict[str, Any]] = []

    for package in resolved["packages"]:
        result = build_package(
            package,
            system_root,
            package_work,
            cache,
            run_tests,
            system_root,
        )
        package_results.append(result)
        if result["status"] != "success":
            system_result = {
                "schema_version": 1,
                "status": "failure",
                "package_set": resolved["package_set"],
                "version_manifest": resolved["version_manifest"],
                "initial_root_sha256": initial_digest,
                "failed_package": package["name"],
                "packages": package_results,
            }
            result_path.write_text(
                json.dumps(system_result, indent=2, sort_keys=True) + "
"
            )
            return system_result

    final_digest = snapshot_digest(snapshot(system_root))
    system_result = {
        "schema_version": 1,
        "status": "success",
        "package_set": resolved["package_set"],
        "version_manifest": resolved["version_manifest"],
        "initial_root_sha256": initial_digest,
        "final_root_sha256": final_digest,
        "root": str(system_root),
        "packages": package_results,
    }
    result_path.write_text(
        json.dumps(system_result, indent=2, sort_keys=True) + "
"
    )
    return system_result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="execute normalized LFS package set in declared order"
    )
    parser.add_argument("--root", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/lfs-optimize-work"))
    parser.add_argument("--cache", type=Path, default=Path("/tmp/lfs-optimize-cache"))
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--versions", type=Path, default=HERE / "versions" / "development.json")
    parser.add_argument("--package-set", type=Path, default=HERE / "package-set.json")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()

    run_tests = not args.skip_tests
    if args.plan:
        result = plan_system(run_tests, args.versions, args.package_set)
    else:
        if args.root is None:
            parser.error("--root is required unless --plan is used")
        result = build_system(
            args.root, args.work, args.cache, run_tests, args.versions, args.package_set
        )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
