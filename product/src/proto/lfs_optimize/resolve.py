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


def substitute_string(value: str, variables: dict[str, str]) -> str:
    result: list[str] = []
    index = 0
    length = len(value)

    while index < length:
        if value.startswith("{{", index):
            result.append("{")
            index += 2
            continue
        if value.startswith("}}", index):
            result.append("}")
            index += 2
            continue
        if value[index] == "{":
            end = value.find("}", index + 1)
            if end != -1:
                key = value[index + 1:end]
                if (
                    key
                    and (key[0].isalpha() or key[0] == "_")
                    and all(char.isalnum() or char == "_" for char in key[1:])
                    and key in variables
                ):
                    result.append(variables[key])
                    index = end + 1
                    continue
        result.append(value[index])
        index += 1

    return "".join(result)


def substitute(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        return substitute_string(value, variables)
    if isinstance(value, list):
        return [substitute(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item, variables) for key, item in value.items()}
    return value


def resolve_parameters(
    name: str,
    definition: dict[str, Any],
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    specs = definition.get("parameters", {})
    if not isinstance(specs, dict):
        raise RuntimeError(f"invalid package parameters: {name}")
    overrides = overrides or {}
    unknown = sorted(set(overrides) - set(specs))
    if unknown:
        raise RuntimeError(
            f"unknown package parameter(s) for {name}: " + ", ".join(unknown)
        )

    values: dict[str, str] = {}
    for parameter, spec in specs.items():
        if not isinstance(parameter, str) or not parameter or not isinstance(spec, dict):
            raise RuntimeError(f"invalid package parameter definition: {name}")
        default = spec.get("default")
        allowed = spec.get("values")
        if (
            not isinstance(default, str)
            or not default
            or not isinstance(allowed, list)
            or not allowed
            or not all(isinstance(item, str) and item for item in allowed)
            or len(allowed) != len(set(allowed))
            or default not in allowed
        ):
            raise RuntimeError(f"invalid package parameter {name}.{parameter}")
        selected = overrides.get(parameter, default)
        if selected not in allowed:
            raise RuntimeError(
                f"invalid package parameter {name}.{parameter}: {selected}"
            )
        values[parameter] = selected
    return values


def resolve_package(
    name: str,
    versions: dict[str, Any],
    parameter_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
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

    parameter_values = resolve_parameters(name, definition, parameter_overrides)
    resolved_definition = copy.deepcopy(definition)
    resolved_definition.pop("parameters", None)
    resolved = substitute(
        resolved_definition,
        {"version": version, **parameter_values},
    )
    if parameter_values:
        resolved["parameters"] = parameter_values
    resolved["version"] = version
    resolved["source"] = copy.deepcopy(source)
    resolved["resources"] = copy.deepcopy(selected.get("resources", {}))
    resolved["reference_metrics"] = copy.deepcopy(selected.get("reference_metrics", {}))
    return resolved


def resolve(package_names: list[str] | None = None,
            versions_path: Path | None = None,
            package_set_path: Path | None = None,
            parameter_overrides: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    package_set = load_json(package_set_path or HERE / "package-set.json")
    versions_doc = load_json(versions_path or HERE / "versions" / "development.json")
    versions = versions_doc.get("packages")
    if not isinstance(versions, dict):
        raise RuntimeError("version manifest packages must be an object")

    package_set_names = package_set.get("packages")
    if not isinstance(package_set_names, list) or not package_set_names:
        raise RuntimeError("package set must contain packages")
    if len(package_set_names) != len(set(package_set_names)):
        raise RuntimeError("package set contains duplicate packages")

    selected = package_names or package_set_names
    if not isinstance(selected, list) or not selected:
        raise RuntimeError("package set must contain packages")

    known = set(package_set_names)
    unknown = [name for name in selected if name not in known]
    if unknown:
        raise RuntimeError("unknown package(s): " + ", ".join(unknown))

    missing_versions = [name for name in package_set_names if name not in versions]
    extra_versions = [name for name in versions if name not in known]
    if missing_versions or extra_versions:
        details = []
        if missing_versions:
            details.append("missing versions: " + ", ".join(missing_versions))
        if extra_versions:
            details.append("unmanaged versions: " + ", ".join(extra_versions))
        raise RuntimeError("package set/version manifest mismatch (" + "; ".join(details) + ")")

    parameter_overrides = parameter_overrides or {}
    unknown_override_packages = sorted(set(parameter_overrides) - set(selected))
    if unknown_override_packages:
        raise RuntimeError(
            "parameter overrides for unselected package(s): "
            + ", ".join(unknown_override_packages)
        )

    return {
        "schema_version": 1,
        "package_set": package_set["name"],
        "version_manifest": versions_doc["name"],
        "basis": versions_doc.get("basis"),
        "packages": [
            resolve_package(name, versions, parameter_overrides.get(name))
            for name in selected
        ],
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
    parser.add_argument(
        "--package-set",
        type=Path,
        default=HERE / "package-set.json",
    )
    args = parser.parse_args()

    try:
        result = resolve(args.packages, args.versions, args.package_set)
    except RuntimeError as exc:
        parser.error(str(exc))

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
