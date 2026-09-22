#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from discover import discover_package
from execute import execute_recipe
from package import find_repository_record, load_repository_records, publish_repository
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
        default=Path.home() / "distro-g1-chroot",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
    )
    parser.add_argument(
        "--chroot-root",
        type=Path,
        help="execute recipe build commands inside this installed G1 root",
    )
    parser.add_argument(
        "--seed-output",
        type=Path,
        help=(
            "reuse exact package selections from this prior build output; "
            "defaults to ~/distro-g1-chroot for chroot builds"
        ),
    )
    parser.add_argument(
        "--pkg",
        action="append",
        dest="packages",
        metavar="NAME",
        help="build only this manifest package; may be repeated",
    )
    parser.add_argument(
        "--force",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help="rebuild these selected packages even when the exact identity is published",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    args.output.mkdir(parents=True, exist_ok=True)

    seed_output = args.seed_output
    if args.chroot_root is not None and seed_output is None:
        seed_output = Path.home() / "distro-g1-chroot"

    manifest_packages = manifest["packages"]
    package_by_name = {package["name"]: package for package in manifest_packages}
    requested = args.packages or []
    forced = [
        name
        for value in args.force
        for name in (part.strip() for part in value.split(","))
        if name
    ]
    forced = list(dict.fromkeys(forced))

    unknown = [
        name
        for name in requested + forced
        if name not in package_by_name
    ]
    if unknown:
        parser.error(
            "unknown manifest package(s): " + ", ".join(sorted(set(unknown)))
        )

    if requested:
        selected_names = list(dict.fromkeys(requested))
        outside_selection = [name for name in forced if name not in selected_names]
        if outside_selection:
            parser.error(
                "--force package(s) must also be selected by --pkg: "
                + ", ".join(outside_selection)
            )
        selected_packages = [package_by_name[name] for name in selected_names]
    else:
        selected_packages = manifest_packages

    force_set = set(forced)
    partial = bool(requested)

    derived = []
    for package in selected_packages:
        if seed_output is None:
            print(
                f"==> {package['name']}: resolve {package['management']}",
                flush=True,
            )
            selected = discover_package(package)
        else:
            seed_recipe_path = seed_output / "recipes" / f"{package['name']}.json"
            if not seed_recipe_path.is_file():
                raise RuntimeError(
                    f"{package['name']}: seed recipe not found: {seed_recipe_path}"
                )
            seed_recipe = json.loads(
                seed_recipe_path.read_text(encoding="utf-8")
            )
            if seed_recipe.get("identity", {}).get("name") != package["name"]:
                raise RuntimeError(
                    f"{package['name']}: seed recipe identity mismatch: "
                    f"{seed_recipe_path}"
                )
            print(
                f"==> {package['name']}: reuse G1 selection "
                f"{seed_recipe['identity']['version']}",
                flush=True,
            )
            selected = {
                "name": package["name"],
                "management": package["management"],
                "version": seed_recipe["identity"]["version"],
                "source_url": seed_recipe["source"]["url"],
                "discovery_url": seed_recipe["discovery"]["discovery_url"],
            }
        derived.append(derive_recipe(selected, args.output))

    builds = []
    skipped = []
    for package in derived:
        recipe_path = Path(package["recipe"])
        recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
        identity = recipe["identity"]
        cached = (
            None
            if identity["name"] in force_set
            else find_repository_record(args.output, identity)
        )
        if identity["name"] in force_set:
            print(
                f"==> {identity['name']}: forced rebuild; bypass repository cache",
                flush=True,
            )
        if cached is not None:
            print(
                f"==> {identity['name']}: repository hit "
                f"{identity['version']}-{identity['architecture']}-{identity['revision']}; "
                "skip build",
                flush=True,
            )
            skipped.append(
                {
                    "name": identity["name"],
                    "version": identity["version"],
                    "architecture": identity["architecture"],
                    "revision": identity["revision"],
                    "artifact": cached["artifact"],
                    "artifact_sha256": cached["artifact_sha256"],
                    "reason": "exact package identity already published",
                    "status": "skipped",
                }
            )
            continue
        builds.append(
            execute_recipe(
                recipe_path,
                args.output,
                args.jobs,
                chroot_root=args.chroot_root,
            )
        )

    failed = [build for build in builds if build["status"] != "success"]
    runtime = None
    repository = None
    if not failed:
        if builds:
            providers = load_repository_records(args.output)
            print("==> verify selected runtime closure", flush=True)
            runtime = verify_runtime_closure(builds, providers)
        else:
            runtime = {
                "dependencies": {},
                "missing": [],
                "status": "success",
            }

    if builds and not failed and runtime["status"] == "success":
        print("==> publish repository update", flush=True)
        repository = publish_repository(
            builds,
            manifest,
            args.output,
            incremental=True,
        )

    if failed:
        status = "build-failures"
    elif runtime["status"] != "success":
        status = "runtime-closure-failures"
    elif not builds:
        status = "up-to-date"
    elif partial:
        status = "published-partial"
    else:
        status = "published"

    result = {
        "status": status,
        "operation": "build",
        "manifest": manifest["name"],
        "output": str(args.output),
        "jobs": args.jobs,
        "chroot_root": (
            str(args.chroot_root.resolve())
            if args.chroot_root is not None
            else None
        ),
        "seed_output": (
            str(seed_output.resolve())
            if seed_output is not None
            else None
        ),
        "selected_packages": [package["name"] for package in selected_packages],
        "partial": partial,
        "forced_packages": forced,
        "packages": skipped + builds,
        "failed_packages": [build["name"] for build in failed],
        "runtime": runtime,
        "repository": repository,
        "next": (
            "refine candidate recipes from build evidence"
            if failed
            else (
                "refine recipes from runtime closure evidence"
                if runtime["status"] != "success"
                else (
                    "build remaining manifest packages: "
                    + ", ".join(repository["missing_packages"])
                    if repository is not None and not repository["complete"]
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
