#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from resolve import HERE, load_json, resolve


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    package_set = load_json(HERE / "package-set.json")
    versions_doc = load_json(HERE / "versions" / "development.json")

    names = package_set.get("packages")
    require(isinstance(names, list) and names, "package set must be non-empty")
    require(len(names) == len(set(names)), "package set contains duplicates")

    versions = versions_doc.get("packages")
    require(isinstance(versions, dict), "development packages must be an object")
    require(set(names) == set(versions), "package set/version manifest mismatch")

    for name in names:
        path = HERE / "packages" / f"{name}.json"
        definition = load_json(path)
        require(definition.get("name") == name, f"{name}: identity mismatch")

        # The package definition owns package/build semantics, not a concrete
        # selected version or source artifact.
        for forbidden in ("version", "source", "resources", "reference_metrics"):
            require(forbidden not in definition, f"{name}: {forbidden} belongs in version manifest")

        procedure = definition.get("procedure")
        require(isinstance(procedure, list) and procedure, f"{name}: missing procedure")
        for index, step in enumerate(procedure):
            require(isinstance(step.get("phase"), str), f"{name}: step {index}: missing phase")
            commands = step.get("commands")
            require(
                isinstance(commands, list)
                and commands
                and all(isinstance(command, str) and command for command in commands),
                f"{name}: step {index}: invalid commands",
            )
            resource = step.get("resource")
            if resource is not None:
                selected_resources = versions[name].get("resources", {})
                require(resource in selected_resources, f"{name}: unresolved resource {resource}")

        selected = versions[name]
        require(isinstance(selected.get("version"), str) and selected["version"], f"{name}: invalid version")
        source = selected.get("source")
        require(isinstance(source, dict), f"{name}: missing source")
        require(isinstance(source.get("url"), str) and source["url"], f"{name}: missing source URL")
        md5 = source.get("md5")
        require(isinstance(md5, str) and len(md5) == 32, f"{name}: invalid source MD5")

        for resource_name, resource in selected.get("resources", {}).items():
            require(isinstance(resource.get("url"), str) and resource["url"], f"{name}/{resource_name}: missing URL")
            checksum = resource.get("md5")
            require(isinstance(checksum, str) and len(checksum) == 32, f"{name}/{resource_name}: invalid MD5")

    result = resolve()
    require(len(result["packages"]) == len(names), "resolver did not return full package set")

    print(json.dumps({
        "status": "success",
        "milestone": "model-proof",
        "packages": names,
        "version_manifest": versions_doc["name"],
        "basis": versions_doc.get("basis"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
