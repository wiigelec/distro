#!/usr/bin/env python3
from __future__ import annotations

import json

from artifact import self_test as artifact_self_test
from development import (
    definition_hashes,
    definition_state_document,
    promotion_transaction_self_test,
    verify_definition_state,
)
from execute import command_failure_disposition, plan
from presentation import self_test as presentation_self_test
from resolve import HERE, load_json, resolve
from system import plan_system

DEPENDENCY_CLASSES = ("build", "runtime", "test", "before", "optional")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    package_set = load_json(HERE / "package-set.json")
    versions_doc = load_json(HERE / "versions" / "development.json")

    names = package_set.get("packages")
    require(isinstance(names, list) and names, "package set must be non-empty")
    require(len(names) == len(set(names)), "package set contains duplicates")
    require(len(names) >= 5, "model proof requires at least five packages")

    versions = versions_doc.get("packages")
    require(isinstance(versions, dict), "development packages must be an object")
    require(set(names) == set(versions), "package set/version manifest mismatch")

    definition_state = definition_state_document(names)
    require(
        set(definition_hashes(definition_state)) == set(names),
        "definition state/package set mismatch",
    )
    verify_definition_state(definition_state, names)
    promotion_transaction_self_test()

    for name in names:
        path = HERE / "packages" / f"{name}.json"
        definition = load_json(path)
        require(definition.get("name") == name, f"{name}: identity mismatch")

        for forbidden in ("version", "source", "resources", "reference_metrics"):
            require(forbidden not in definition, f"{name}: {forbidden} belongs in version manifest")

        require(isinstance(definition.get("description"), str) and definition["description"],
                f"{name}: missing package description")

        dependencies = definition.get("dependencies")
        require(isinstance(dependencies, dict), f"{name}: missing dependency model")
        require(set(dependencies) == set(DEPENDENCY_CLASSES),
                f"{name}: dependency classes mismatch")
        for dep_class in DEPENDENCY_CLASSES:
            require(
                isinstance(dependencies[dep_class], list)
                and all(isinstance(item, str) and item for item in dependencies[dep_class]),
                f"{name}: invalid {dep_class} dependencies",
            )

        parameters = definition.get("parameters", {})
        require(isinstance(parameters, dict), f"{name}: invalid parameters")
        for parameter, spec in parameters.items():
            require(
                isinstance(parameter, str)
                and parameter
                and isinstance(spec, dict),
                f"{name}: invalid parameter definition",
            )
            default = spec.get("default")
            values = spec.get("values")
            require(
                isinstance(default, str)
                and default
                and isinstance(values, list)
                and values
                and all(isinstance(value, str) and value for value in values)
                and len(values) == len(set(values))
                and default in values,
                f"{name}: invalid parameter {parameter}",
            )

        procedure = definition.get("procedure")
        require(isinstance(procedure, list) and procedure, f"{name}: missing procedure")
        seen_command_ids: set[str] = set()
        for index, step in enumerate(procedure):
            require(isinstance(step.get("phase"), str) and step["phase"],
                    f"{name}: step {index}: missing phase")
            working_directory = step.get("working_directory")
            require(
                isinstance(working_directory, str)
                and working_directory
                and not working_directory.startswith("/")
                and "." not in working_directory.split("/")
                and ".." not in working_directory.split("/"),
                f"{name}: step {index}: invalid working directory",
            )
            require(step.get("condition") in ("always", "tests-enabled"),
                    f"{name}: step {index}: invalid condition")
            commands = step.get("commands")
            require(isinstance(commands, list) and commands,
                    f"{name}: step {index}: invalid commands")
            for command_index, command in enumerate(commands):
                require(isinstance(command, dict),
                        f"{name}: step {index}/{command_index}: command must be structured")
                require(isinstance(command.get("command"), str) and command["command"],
                        f"{name}: step {index}/{command_index}: missing command")
                require(command.get("user") in ("root", "tester"),
                        f"{name}: step {index}/{command_index}: invalid user")
                command_id = command.get("id")
                if command_id is not None:
                    require(isinstance(command_id, str) and command_id,
                            f"{name}: step {index}/{command_index}: invalid command id")
                    require(command_id not in seen_command_ids,
                            f"{name}: duplicate command id {command_id}")
                    seen_command_ids.add(command_id)
                kind = command.get("kind")
                require(kind in (None, "session-transition"),
                        f"{name}: step {index}/{command_index}: invalid command kind")
                if kind == "session-transition":
                    require(step["phase"] == "system",
                            f"{name}: session transition must be a system step")
                environment = command.get("environment")
                if environment is not None:
                    require(
                        isinstance(environment, dict)
                        and all(isinstance(k, str) and isinstance(v, str)
                                for k, v in environment.items()),
                        f"{name}: step {index}/{command_index}: invalid environment",
                    )
            resource = step.get("resource")
            if resource is not None:
                selected_resources = versions[name].get("resources", {})
                require(resource in selected_resources,
                        f"{name}: unresolved resource {resource}")

        installed_descriptions = definition.get("installed_descriptions")
        require(isinstance(installed_descriptions, list),
                f"{name}: missing installed-item descriptions")
        for item in installed_descriptions:
            require(
                isinstance(item, dict)
                and isinstance(item.get("id"), str) and item["id"]
                and isinstance(item.get("name"), str) and item["name"]
                and isinstance(item.get("description"), str) and item["description"],
                f"{name}: invalid installed-item description",
            )
            item_kind = item.get("kind")
            if item_kind is not None:
                require(item_kind in ("program", "library", "file", "directory"),
                        f"{name}: invalid installed-item kind")

        selected = versions[name]
        require(isinstance(selected.get("version"), str) and selected["version"],
                f"{name}: invalid version")
        source = selected.get("source")
        require(isinstance(source, dict), f"{name}: missing source")
        for field in ("url", "home", "size"):
            require(isinstance(source.get(field), str) and source[field],
                    f"{name}: missing source {field}")
        md5 = source.get("md5")
        require(isinstance(md5, str) and len(md5) == 32,
                f"{name}: invalid source MD5")

        for resource_name, resource in selected.get("resources", {}).items():
            require(isinstance(resource.get("url"), str) and resource["url"],
                    f"{name}/{resource_name}: missing URL")
            checksum = resource.get("md5")
            require(isinstance(checksum, str) and len(checksum) == 32,
                    f"{name}/{resource_name}: invalid MD5")

    result = resolve()
    require(len(result["packages"]) == len(names),
            "resolver did not return full package set")

    groff_default = resolve(["groff"])["packages"][0]
    require(
        groff_default.get("parameters") == {"paper_size": "letter"},
        "groff: default paper-size parameter drift",
    )
    default_plan = plan(groff_default, run_tests=True)
    require(
        default_plan["commands"][0]["command"]
        == "PAGE=letter ./configure --prefix=/usr",
        "groff: default paper-size execution drift",
    )
    groff_a4 = resolve(
        ["groff"],
        parameter_overrides={"groff": {"paper_size": "A4"}},
    )["packages"][0]
    require(
        groff_a4.get("parameters") == {"paper_size": "A4"}
        and plan(groff_a4, run_tests=True)["commands"][0]["command"]
        == "PAGE=A4 ./configure --prefix=/usr",
        "groff: paper-size override execution drift",
    )
    try:
        resolve(
            ["groff"],
            parameter_overrides={"groff": {"paper_size": "legal"}},
        )
    except RuntimeError:
        pass
    else:
        raise RuntimeError("groff: invalid paper-size parameter accepted")

    glibc_resolved = resolve(["glibc"])["packages"][0]
    glibc_upgrade = glibc_resolved["supplemental_procedures"][
        "upgrade-gcc-fixed-headers"
    ]["procedure"][0]["commands"][0]["command"]
    require(
        "include{-fixed,}/limits.h" in glibc_upgrade
        and "include{-fixed,}/syslimits.h" in glibc_upgrade,
        "resolver: shell brace expansion was mistaken for a package parameter",
    )

    binutils_resolved = resolve(["binutils"])["packages"][0]
    binutils_commands = [
        command["command"]
        for step in binutils_resolved["procedure"]
        for command in step["commands"]
    ]
    require(
        any(
            "lib{bfd,ctf,ctf-nobfd,gprofng,opcodes,sframe}.a" in command
            for command in binutils_commands
        ),
        "resolver: escaped literal braces were not restored",
    )

    pkgconf_resolved = resolve(["pkgconf"])["packages"][0]
    pkgconf_commands = [
        command["command"]
        for step in pkgconf_resolved["procedure"]
        for command in step["commands"]
    ]
    require(
        any(
            f"pkgconf{{,-{pkgconf_resolved['version']}}}" in command
            for command in pkgconf_commands
        ),
        "resolver: nested parameter inside escaped shell braces drifted",
    )

    artifact_self_test()
    presentation_self_test()
    for package in result["packages"]:
        execution_plan = plan(package, run_tests=True)
        require(execution_plan["status"] == "success",
                f"{package['name']}: execution plan failed")
        require(execution_plan["commands"],
                f"{package['name']}: execution plan is empty")

    require(command_failure_disposition("test") == "review",
            "test command failures must be review evidence")
    require(command_failure_disposition("build") == "fatal",
            "non-test command failures must remain fatal")

    system_plan = plan_system(run_tests=True)
    require(system_plan["status"] == "success",
            "system execution plan failed")
    require(
        [item["package"] for item in system_plan["packages"]] == names,
        "system execution plan does not preserve package-set order",
    )

    print(json.dumps({
        "status": "success",
        "milestone": "model-proof",
        "packages": names,
        "version_manifest": versions_doc["name"],
        "basis": versions_doc.get("basis"),
        "invariants": {
            "version_independent_definitions": True,
            "structured_execution": True,
            "dependency_classes": list(DEPENDENCY_CLASSES),
            "presentation_document_identity_independent": True,
            "package_and_installed_descriptions": True,
            "ordered_system_execution": True,
        },
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
