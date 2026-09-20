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
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    args.output.mkdir(parents=True, exist_ok=True)

    derived = []
    for package in manifest["packages"]:
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
    if not failed:
        print("==> verify staged runtime closure", flush=True)
        runtime = verify_runtime_closure(builds)

    if not failed and runtime["status"] == "success":
        print("==> publish prototype repository", flush=True)
        repository = publish_repository(builds, manifest, args.output)

    status = "build-failures" if failed else (
        "runtime-closure-failures"
        if runtime["status"] != "success"
        else "published"
    )

    result = {
        "status": status,
        "operation": "build",
        "manifest": manifest["name"],
        "output": str(args.output),
        "jobs": args.jobs,
        "packages": builds,
        "failed_packages": [build["name"] for build in failed],
        "runtime": runtime,
        "repository": repository,
        "next": (
            "refine candidate recipes from build evidence"
            if failed
            else (
                "refine recipes from runtime closure evidence"
                if runtime["status"] != "success"
                else f"./product/scripts/manage install {manifest['name']}"
            )
        ),
    }

    result_path = args.output / "result.json"
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if status != "published" else 0


if __name__ == "__main__":
    raise SystemExit(main())
