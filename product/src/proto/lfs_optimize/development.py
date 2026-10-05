#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from resolve import load_json
from system import build_system, plan_system

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def package_versions(document: dict[str, Any]) -> dict[str, str]:
    packages = document.get("packages")
    if not isinstance(packages, dict):
        raise RuntimeError("version manifest packages must be an object")
    result: dict[str, str] = {}
    for name, selected in packages.items():
        if not isinstance(name, str) or not name or not isinstance(selected, dict):
            raise RuntimeError("invalid package version entry")
        version = selected.get("version")
        if not isinstance(version, str) or not version:
            raise RuntimeError(f"{name}: missing version")
        result[name] = version
    return result


def package_names(document: dict[str, Any]) -> list[str]:
    names = document.get("packages")
    if not isinstance(names, list) or not names:
        raise RuntimeError("package set must contain packages")
    if len(names) != len(set(names)):
        raise RuntimeError("package set contains duplicates")
    return names


def definition_hashes(document: dict[str, Any]) -> dict[str, str]:
    packages = document.get("packages")
    if not isinstance(packages, dict):
        raise RuntimeError("definition state packages must be an object")
    result: dict[str, str] = {}
    for name, selected in packages.items():
        if not isinstance(name, str) or not name or not isinstance(selected, dict):
            raise RuntimeError("invalid definition state entry")
        sha256 = selected.get("sha256")
        if (
            not isinstance(sha256, str)
            or len(sha256) != 64
            or any(char not in "0123456789abcdef" for char in sha256)
        ):
            raise RuntimeError(f"{name}: invalid definition SHA256")
        result[name] = sha256
    return result


def definition_state_document(
    names: list[str], definitions_dir: Path = HERE / "packages"
) -> dict[str, Any]:
    packages: dict[str, dict[str, str]] = {}
    for name in names:
        path = definitions_dir / f"{name}.json"
        if not path.is_file():
            raise RuntimeError(f"{name}: package definition is missing")
        definition = load_json(path)
        if definition.get("name") != name:
            raise RuntimeError(f"{name}: package definition identity mismatch")
        packages[name] = {"sha256": digest(path)}
    return {
        "schema_version": 1,
        "record_type": "definition-state",
        "packages": packages,
    }


def verify_definition_state(
    document: dict[str, Any], names: list[str], definitions_dir: Path = HERE / "packages"
) -> None:
    expected = definition_hashes(document)
    if set(expected) != set(names):
        raise RuntimeError("definition state/package-set mismatch")
    observed = definition_hashes(definition_state_document(names, definitions_dir))
    changed = [name for name in names if expected[name] != observed[name]]
    if changed:
        raise RuntimeError(
            "package definitions changed after discovery: " + ", ".join(changed)
        )


def bind_definitions(
    package_set_path: Path, output_path: Path, definitions_dir: Path
) -> dict[str, Any]:
    if output_path.exists():
        raise RuntimeError("definition state output already exists")
    names = package_names(load_json(package_set_path))
    state = definition_state_document(names, definitions_dir)
    write_json(output_path, state)
    return {
        "schema_version": 1,
        "status": "success",
        "operation": "bind-definitions",
        "definition_state": str(output_path),
        "definition_state_sha256": digest(output_path),
    }


def seed(baseline_path: Path, state_dir: Path) -> dict[str, Any]:
    baseline = load_json(baseline_path)
    package_set = baseline.get("package_set")
    packages = baseline.get("packages")
    if not isinstance(package_set, dict) or not isinstance(packages, dict):
        raise RuntimeError("baseline must contain package_set and packages")
    state_dir.mkdir(parents=True, exist_ok=False)
    development_path = state_dir / "development.json"
    package_set_path = state_dir / "package-set.json"
    definition_state_path = state_dir / "definition-state.json"
    write_json(package_set_path, {
        "schema_version": 1,
        "name": package_set.get("name", "development-proof"),
        "packages": package_set.get("packages"),
    })
    write_json(development_path, {
        "schema_version": 1,
        "name": "development",
        "basis": baseline.get("basis"),
        "packages": packages,
    })
    # The historical M5 seed predates normalized package definitions for every
    # baseline package. Discovery may migrate this one legacy state; promotion
    # always writes a fully bound definition state.
    write_json(definition_state_path, {
        "schema_version": 1,
        "record_type": "definition-state",
        "legacy_unbound": True,
        "packages": {},
    })
    return {
        "schema_version": 1,
        "status": "success",
        "operation": "seed",
        "development": str(development_path),
        "package_set": str(package_set_path),
        "definition_state": str(definition_state_path),
    }


def discover(
    development_path: Path,
    package_set_path: Path,
    definition_state_path: Path,
    proposal_versions_path: Path,
    proposal_package_set_path: Path,
    proposal_definitions_dir: Path,
    candidate_dir: Path,
) -> dict[str, Any]:
    current_versions = load_json(development_path)
    current_set = load_json(package_set_path)
    current_definition_state = load_json(definition_state_path)
    proposal_versions = load_json(proposal_versions_path)
    proposal_set = load_json(proposal_package_set_path)

    current_names = package_names(current_set)
    proposal_names = package_names(proposal_set)
    current = package_versions(current_versions)
    proposal = package_versions(proposal_versions)
    current_definitions = definition_hashes(current_definition_state)

    if set(current_names) != set(current):
        raise RuntimeError("current package set/version manifest mismatch")
    if set(proposal_names) != set(proposal):
        raise RuntimeError("proposal package set/version manifest mismatch")
    if current_definition_state.get("legacy_unbound") is not True:
        if set(current_names) != set(current_definitions):
            raise RuntimeError("current package set/definition state mismatch")

    proposal_definition_state = definition_state_document(
        proposal_names, proposal_definitions_dir
    )
    proposal_definitions = definition_hashes(proposal_definition_state)

    added = [name for name in proposal_names if name not in current]
    removed = [name for name in current_names if name not in proposal]
    changed = [
        {"package": name, "from": current[name], "to": proposal[name]}
        for name in proposal_names
        if name in current and current[name] != proposal[name]
    ]
    definition_changes = [
        {
            "package": name,
            "from": current_definitions.get(name),
            "to": proposal_definitions[name],
        }
        for name in proposal_names
        if current_definitions.get(name) != proposal_definitions[name]
    ]
    unchanged = [
        name
        for name in proposal_names
        if name in current
        and current[name] == proposal[name]
        and current_definitions.get(name) == proposal_definitions[name]
    ]

    candidate_dir.mkdir(parents=True, exist_ok=False)
    candidate_versions = candidate_dir / "versions.json"
    candidate_set = candidate_dir / "package-set.json"
    candidate_definitions = candidate_dir / "definition-state.json"
    shutil.copyfile(proposal_versions_path, candidate_versions)
    shutil.copyfile(proposal_package_set_path, candidate_set)
    write_json(candidate_definitions, proposal_definition_state)

    candidate_id = hashlib.sha256(
        candidate_versions.read_bytes()
        + b"\0"
        + candidate_set.read_bytes()
        + b"\0"
        + candidate_definitions.read_bytes()
    ).hexdigest()
    record = {
        "schema_version": 1,
        "record_type": "development-candidate",
        "status": "proposed",
        "candidate_id": candidate_id,
        "baseline": {
            "development": str(development_path),
            "development_sha256": digest(development_path),
            "package_set": str(package_set_path),
            "package_set_sha256": digest(package_set_path),
            "definition_state": str(definition_state_path),
            "definition_state_sha256": digest(definition_state_path),
            "basis": current_versions.get("basis"),
        },
        "proposal": {
            "versions": str(candidate_versions),
            "versions_sha256": digest(candidate_versions),
            "package_set": str(candidate_set),
            "package_set_sha256": digest(candidate_set),
            "definition_state": str(candidate_definitions),
            "definition_state_sha256": digest(candidate_definitions),
            "basis": proposal_versions.get("basis"),
        },
        "changes": {
            "added": added,
            "removed": removed,
            "version_changes": changed,
            "definition_changes": definition_changes,
            "unchanged_count": len(unchanged),
        },
    }
    write_json(candidate_dir / "candidate.json", record)
    return record


def load_candidate(path: Path) -> dict[str, Any]:
    candidate = load_json(path)
    if candidate.get("record_type") != "development-candidate":
        raise RuntimeError("not a development candidate record")
    proposal = candidate["proposal"]
    versions = Path(proposal["versions"])
    package_set = Path(proposal["package_set"])
    definition_state = Path(proposal["definition_state"])
    if digest(versions) != proposal.get("versions_sha256"):
        raise RuntimeError("candidate versions changed after discovery")
    if digest(package_set) != proposal.get("package_set_sha256"):
        raise RuntimeError("candidate package set changed after discovery")
    if digest(definition_state) != proposal.get("definition_state_sha256"):
        raise RuntimeError("candidate definition state changed after discovery")
    return candidate


def validate_candidate(
    candidate_path: Path,
    root: Path | None,
    work: Path,
    cache: Path,
    plan_only: bool,
    run_tests: bool,
    definitions_dir: Path,
) -> dict[str, Any]:
    candidate = load_candidate(candidate_path)
    versions = Path(candidate["proposal"]["versions"])
    package_set = Path(candidate["proposal"]["package_set"])
    definition_state = Path(candidate["proposal"]["definition_state"])
    names = package_names(load_json(package_set))
    verify_definition_state(load_json(definition_state), names, definitions_dir)
    if plan_only:
        system_result = plan_system(run_tests, versions, package_set)
        mode = "plan"
    else:
        if root is None:
            raise RuntimeError("--root is required for build validation")
        system_result = build_system(root, work, cache, run_tests, versions, package_set)
        mode = "build"
    result = {
        "schema_version": 1,
        "record_type": "candidate-validation",
        "status": system_result["status"],
        "candidate_id": candidate["candidate_id"],
        "mode": mode,
        "tests_enabled": run_tests,
        "definition_state_sha256": digest(definition_state),
        "system_result": system_result,
        "review_required": system_result.get("review_required", False),
        "test_review": system_result.get("test_review", []),
    }
    write_json(candidate_path.parent / "validation.json", result)
    return result


def promote(
    candidate_path: Path,
    validation_path: Path,
    development_path: Path,
    package_set_path: Path,
    definition_state_path: Path,
) -> dict[str, Any]:
    candidate = load_candidate(candidate_path)
    validation = load_json(validation_path)
    if validation.get("record_type") != "candidate-validation":
        raise RuntimeError("not a candidate validation record")
    if validation.get("candidate_id") != candidate.get("candidate_id"):
        raise RuntimeError("validation does not belong to candidate")
    if validation.get("status") != "success":
        raise RuntimeError("candidate validation did not succeed")
    if validation.get("mode") != "build":
        raise RuntimeError("plan-only validation cannot be promoted")
    if validation.get("tests_enabled") is not True:
        raise RuntimeError("candidate built with tests disabled cannot be promoted")

    proposal = candidate["proposal"]
    if validation.get("definition_state_sha256") != proposal.get("definition_state_sha256"):
        raise RuntimeError("validation definition state does not belong to candidate")

    baseline = candidate["baseline"]
    if digest(development_path) != baseline.get("development_sha256"):
        raise RuntimeError("development state changed since discovery")
    if digest(package_set_path) != baseline.get("package_set_sha256"):
        raise RuntimeError("package-set state changed since discovery")
    if digest(definition_state_path) != baseline.get("definition_state_sha256"):
        raise RuntimeError("definition state changed since discovery")

    shutil.copyfile(Path(proposal["versions"]), development_path)
    shutil.copyfile(Path(proposal["package_set"]), package_set_path)
    shutil.copyfile(Path(proposal["definition_state"]), definition_state_path)

    result = {
        "schema_version": 1,
        "status": "success",
        "operation": "promote",
        "candidate_id": candidate["candidate_id"],
        "development_sha256": digest(development_path),
        "package_set_sha256": digest(package_set_path),
        "definition_state_sha256": digest(definition_state_path),
        "review_required": validation.get("review_required", False),
        "test_review": validation.get("test_review", []),
    }
    write_json(candidate_path.parent / "promotion.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="M5 LFS development-state proof workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("seed")
    p.add_argument(
        "--baseline",
        type=Path,
        default=HERE / "versions" / "lfs-13.0-systemd-baseline.json",
    )
    p.add_argument("--state-dir", type=Path, required=True)

    p = sub.add_parser("bind-definitions")
    p.add_argument("--package-set", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--definitions-dir", type=Path, default=HERE / "packages")

    p = sub.add_parser("discover")
    p.add_argument("--development", type=Path, required=True)
    p.add_argument("--package-set", type=Path, required=True)
    p.add_argument("--definition-state", type=Path, required=True)
    p.add_argument(
        "--proposal-versions",
        type=Path,
        default=HERE / "versions" / "development.json",
    )
    p.add_argument(
        "--proposal-package-set", type=Path, default=HERE / "package-set.json"
    )
    p.add_argument(
        "--proposal-definitions-dir", type=Path, default=HERE / "packages"
    )
    p.add_argument("--candidate-dir", type=Path, required=True)

    p = sub.add_parser("validate")
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--root", type=Path)
    p.add_argument("--work", type=Path, default=Path("/tmp/lfs-m5-work"))
    p.add_argument("--cache", type=Path, default=Path("/tmp/lfs-m5-cache"))
    p.add_argument("--definitions-dir", type=Path, default=HERE / "packages")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--skip-tests", action="store_true")

    p = sub.add_parser("promote")
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--validation", type=Path, required=True)
    p.add_argument("--development", type=Path, required=True)
    p.add_argument("--package-set", type=Path, required=True)
    p.add_argument("--definition-state", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "seed":
            result = seed(args.baseline, args.state_dir)
        elif args.command == "bind-definitions":
            result = bind_definitions(
                args.package_set, args.output, args.definitions_dir
            )
        elif args.command == "discover":
            result = discover(
                args.development,
                args.package_set,
                args.definition_state,
                args.proposal_versions,
                args.proposal_package_set,
                args.proposal_definitions_dir,
                args.candidate_dir,
            )
        elif args.command == "validate":
            result = validate_candidate(
                args.candidate,
                args.root,
                args.work,
                args.cache,
                args.plan,
                not args.skip_tests,
                args.definitions_dir,
            )
        else:
            result = promote(
                args.candidate,
                args.validation,
                args.development,
                args.package_set,
                args.definition_state,
            )
    except RuntimeError as exc:
        print(
            json.dumps(
                {"schema_version": 1, "status": "failure", "error": str(exc)},
                indent=2,
            )
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
