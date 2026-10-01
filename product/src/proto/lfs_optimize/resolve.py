#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise RuntimeError(f"unsupported schema: {path}")
    return value


def substitute(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format_map(variables)
    if isinstance(value, list):
        return [substitute(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item, variables) for key, item in value.items()}
    return value


def resolve_package(name: str, versions: dict[str, Any]) -> dict[str, Any]:
    definition_path = HERE / "packages" / f"{name}.json"
    if not definition_path.is_file():
        raise RuntimeError(f"missing package definition: {name}")

    definition = load_json(definition_path)
    if definition.get("name") != name:
        raise RuntimeError(f"package identity mismatch: {definition_path}")

    selected = versions.get(name)
    if not isinstance(selected, dict):
        raise RuntimeError(f"development version missing for package: {name}")

    version = selected.get("version")
    source = selected.get("source")
    if not isinstance(version, str) or not version:
        raise RuntimeError(f"invalid version selection: {name}")
    if not isinstance(source, dict) or not source.get("url") or not source.get("md5"):
        raise RuntimeError(f"invalid source selection: {name}")

    resolved = substitute(copy.deepcopy(definition), {"version": version})
    resolved["version"] = version
    resolved["source"] = copy.deepcopy(source)
    resolved["resources"] = copy.deepcopy(selected.get("resources", {}))
    resolved["reference_metrics"] = copy.deepcopy(selected.get("reference_metrics", {}))
    return resolved


def resolve(package_names: list[str] | None = None,
            versions_path: Path | None = None) -> dict[str, Any]:
    package_set = load_json(HERE / "package-set.json")
    versions_doc = load_json(versions_path or HERE / "versions" / "development.json")
    versions = versions_doc.get("packages")
    if not isinstance(versions, dict):
        raise RuntimeError("version manifest packages must be an object")

    selected = package_names or package_set.get("packages")
    if not isinstance(selected, list) or not selected:
        raise RuntimeError("package set must contain packages")

    known = set(package_set["packages"])
    unknown = [name for name in selected if name not in known]
    if unknown:
        raise RuntimeError("unknown package(s): " + ", ".join(unknown))

    return {
        "schema_version": 1,
        "package_set": package_set["name"],
        "version_manifest": versions_doc["name"],
        "basis": versions_doc.get("basis"),
        "packages": [resolve_package(name, versions) for name in selected],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="resolve normalized LFS package definitions"
    )
    parser.add_argument("--package", action="append", dest="packages")
    parser.add_argument(
        "--versions",
        type=Path,
        default=HERE / "versions" / "development.json",
    )
    args = parser.parse_args()

    try:
        result = resolve(args.packages, args.versions)
    except RuntimeError as exc:
        parser.error(str(exc))

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
