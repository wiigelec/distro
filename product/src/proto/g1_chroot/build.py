#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from discover import discover_package
from recipe import derive_recipe

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
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    args.output.mkdir(parents=True, exist_ok=True)

    resolved = []
    recipes = []
    for package in manifest["packages"]:
        print(
            f"==> {package['name']}: resolve {package['management']}",
            flush=True,
        )
        selected = discover_package(package)
        resolved.append(selected)
        recipes.append(derive_recipe(selected, args.output))

    result = {
        "status": "recipes-derived",
        "operation": "build",
        "manifest": manifest["name"],
        "output": str(args.output),
        "packages": recipes,
        "next": "execute candidate recipes and refine from build evidence",
    }
    result_path = args.output / "result.json"
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
