#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from discover import discover_package
from execute import execute_recipe
from package import publish_repository
from recipe import derive_recipe
from runtime import verify_runtime_closure

HERE = Path(__file__).resolve().parent
MANAGEMENT_POLICIES = {"stable", "lts", "bleeding-edge"}


def load_manifest(name: str) -> dict:
    path = HERE / f"{name}.json"
    if not path.is_file():
        raise RuntimeError(f"unknown build manifest: {name}")

    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise RuntimeError(f"unsupported manifest schema: {path}")
    if manifest.get("name") != name:
        raise RuntimeError(f"manifest identity mismatch: {path}")

    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        raise RuntimeError("manifest packages must be a non-empty array")

    seen = set()
    for package in packages:
        if set(package) != {"name", "url", "management"}:
            raise RuntimeError(
                "each manifest package must contain exactly name, url, and management"
            )
        if not all(isinstance(package[key], str) and package[key] for key in package):
            raise RuntimeError("manifest package values must be non-empty strings")
        if package["name"] in seen:
            raise RuntimeError(f"duplicate manifest package: {package['name']}")
        seen.add(package["name"])
        if package["management"] not in MANAGEMENT_POLICIES:
            raise RuntimeError(
                f"{package['name']}: unsupported management value "
                f"{package['management']!r}"
            )

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="G1 chroot Build prototype")
    parser.add_argument("manifest")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/distro-g1-chroot"),
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
    )
    parser.add_argument(
        "--pkg",
        action="append",
        dest="packages",
        metavar="NAME",
        help="build only this manifest package; may be repeated",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    args.output.mkdir(parents=True, exist_ok=True)

    manifest_packages = manifest["packages"]
    package_by_name = {package["name"]: package for package in manifest_packages}
    requested = args.packages or []
    unknown = [name for name in requested if name not in package_by_name]
    if unknown:
        parser.error(
            "unknown manifest package(s): " + ", ".join(sorted(set(unknown)))
        )

    selected_packages = (
        [package_by_name[name] for name in dict.fromkeys(requested)]
        if requested
        else manifest_packages
    )
    partial = bool(requested)

    derived = []
    for package in selected_packages:
        print(
            f"==> {package['name']}: resolve {package['management']}",
            flush=True,
        )
        selected = discover_package(package)
        derived.append(derive_recipe(selected, args.output))

    builds = []
    for package in derived:
        recipe_path = Path(package["recipe"])
        builds.append(execute_recipe(recipe_path, args.output, args.jobs))

    failed = [build for build in builds if build["status"] != "success"]
    runtime = None
    repository = None
    if not failed and not partial:
        print("==> verify staged runtime closure", flush=True)
        runtime = verify_runtime_closure(builds)

    if (
        not failed
        and not partial
        and runtime["status"] == "success"
    ):
        print("==> publish prototype repository", flush=True)
        repository = publish_repository(builds, manifest, args.output)

    if failed:
        status = "build-failures"
    elif partial:
        status = "built-partial"
    elif runtime["status"] != "success":
        status = "runtime-closure-failures"
    else:
        status = "published"

    result = {
        "status": status,
        "operation": "build",
        "manifest": manifest["name"],
        "output": str(args.output),
        "jobs": args.jobs,
        "selected_packages": [package["name"] for package in selected_packages],
        "partial": partial,
        "packages": builds,
        "failed_packages": [build["name"] for build in failed],
        "runtime": runtime,
        "repository": repository,
        "next": (
            "refine candidate recipes from build evidence"
            if failed
            else (
                f"./product/scripts/build {manifest['name']}"
                if partial
                else (
                    "refine recipes from runtime closure evidence"
                    if runtime["status"] != "success"
                    else f"./product/scripts/manage install {manifest['name']}"
                )
            )
        ),
    }

    result_path = args.output / "result.json"
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if status in {"build-failures", "runtime-closure-failures"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
