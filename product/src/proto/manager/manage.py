#!/usr/bin/env python3
"""Manage v0: install prototype repository packages into a target root."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path, PurePosixPath


DATABASE_PATH = Path("var/lib/distro/manage/installed.json")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def load_repository(path):
    database = json.loads((path / "database.json").read_text())
    packages = {}
    for package in database.get("packages", []):
        name = package["identity"]["name"]
        if name in packages:
            raise RuntimeError(f"duplicate package in repository: {name}")
        packages[name] = package
    return packages


def load_installed(root):
    path = root / DATABASE_PATH
    if not path.exists():
        return {"schema_version": 1, "packages": []}
    return json.loads(path.read_text())


def safe_relative_path(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not value or value == "." or ".." in path.parts:
        raise RuntimeError(f"invalid target-root-relative path: {value}")
    return path


def safe_symlink_target(member_name, linkname):
    link = PurePosixPath(linkname)

    # Absolute symlinks are valid package payloads: once the target filesystem
    # is used as a process root, /usr/lib/libc.so refers to that target root.
    # Manage never dereferences the link while applying the package.
    if link.is_absolute():
        if ".." in link.parts:
            raise RuntimeError(
                f"package symlink {member_name} has unsafe target {linkname}"
            )
        return

    depth = 0
    for part in (PurePosixPath(member_name).parent / link).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            depth -= 1
            if depth < 1:
                raise RuntimeError(
                    f"package symlink {member_name} escapes payload root"
                )
        else:
            depth += 1


def resolve(requested, packages):
    order = []
    state = {}

    def visit(name):
        if name not in packages:
            raise RuntimeError(f"unsatisfied package dependency: {name}")
        if state.get(name) == "visiting":
            raise RuntimeError(f"dependency cycle involving {name}")
        if state.get(name) == "done":
            return

        state[name] = "visiting"
        for dependency in packages[name].get("depends", []):
            if set(dependency) != {"name"}:
                raise RuntimeError(
                    "Manage v0 supports only unconstrained package-name dependencies"
                )
            visit(dependency["name"])
        state[name] = "done"
        order.append(name)

    visit(requested)
    return order


def inspect_artifact(repository, package):
    artifact = repository / package["artifact"]
    actual = sha256_file(artifact)
    if actual != package["artifact_sha256"]:
        raise RuntimeError(
            f"artifact checksum mismatch for {package['identity']['name']}"
        )

    payload_paths = set()
    embedded_identity = None

    with tarfile.open(artifact, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "metadata.json":
                metadata_file = tar.extractfile(member)
                if metadata_file is None:
                    raise RuntimeError("metadata.json is unreadable")
                embedded_identity = json.load(metadata_file).get("identity")
                continue

            if member.name in {"root", "root/"}:
                continue
            if not member.name.startswith("root/"):
                raise RuntimeError(
                    f"unexpected member outside payload root: {member.name}"
                )

            relative = member.name[len("root/"):]
            safe_relative_path(relative)

            if member.issym():
                safe_symlink_target(member.name, member.linkname)
            elif member.islnk():
                raise RuntimeError("Manage v0 rejects hard links")
            elif not (member.isdir() or member.isfile()):
                raise RuntimeError(f"unsupported archive member: {member.name}")

            if member.isfile() or member.issym():
                payload_paths.add(relative)

    if embedded_identity != package["identity"]:
        raise RuntimeError(
            f"embedded identity mismatch for {package['identity']['name']}"
        )

    declared = set(package.get("owned_paths", []))
    if payload_paths != declared:
        raise RuntimeError(
            f"payload inventory mismatch for {package['identity']['name']}"
        )

    return artifact


def preflight(plan, packages, installed):
    installed_owners = {}
    for record in installed.get("packages", []):
        for path in record.get("owned_paths", []):
            installed_owners[path] = record["identity"]["name"]

    planned_owners = {}
    for name in plan:
        for path in packages[name].get("owned_paths", []):
            existing = installed_owners.get(path)
            if existing and existing != name:
                raise RuntimeError(
                    f"owned path conflict: {path} already belongs to {existing}"
                )
            planned = planned_owners.get(path)
            if planned and planned != name:
                raise RuntimeError(
                    f"transaction path conflict: {path} claimed by "
                    f"{planned} and {name}"
                )
            planned_owners[path] = name


def apply_artifact(root, artifact):
    with tarfile.open(artifact, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.name.startswith("root/"):
                continue
            relative = member.name[len("root/"):]
            if not relative:
                continue
            safe_relative_path(relative)
            target = root / relative

            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                os.chmod(target, member.mode & 0o7777)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)

            if member.issym():
                safe_symlink_target(member.name, member.linkname)
                if target.exists() or target.is_symlink():
                    target.unlink()
                os.symlink(member.linkname, target)
                continue

            if member.isfile():
                source = tar.extractfile(member)
                if source is None:
                    raise RuntimeError(f"unable to read {member.name}")
                with target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                os.chmod(target, member.mode & 0o7777)
                continue

            raise RuntimeError(f"unsupported payload member: {member.name}")


def install(repository, root, requested):
    repository = repository.resolve()
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)

    packages = load_repository(repository)
    installed = load_installed(root)
    plan = resolve(requested, packages)

    artifacts = {
        name: inspect_artifact(repository, packages[name])
        for name in plan
    }
    preflight(plan, packages, installed)

    records = {
        record["identity"]["name"]: record
        for record in installed.get("packages", [])
    }

    for name in plan:
        package = packages[name]
        current = records.get(name)

        if current and current["identity"] == package["identity"]:
            if name == requested and current["install_reason"] == "dependency":
                current["install_reason"] = "explicit"
            continue

        apply_artifact(root, artifacts[name])
        records[name] = {
            "identity": package["identity"],
            "artifact_checksum": package["artifact_sha256"],
            "install_reason": "explicit" if name == requested else "dependency",
            "held": False,
            "depends": package.get("depends", []),
            "conflicts": package.get("conflicts", []),
            "provides": package.get("provides", []),
            "owned_paths": package.get("owned_paths", []),
        }

    installed_result = {
        "schema_version": 1,
        "packages": sorted(
            records.values(),
            key=lambda record: record["identity"]["name"],
        ),
    }
    write_json(root / DATABASE_PATH, installed_result)

    return {
        "schema_version": 1,
        "status": "success",
        "root": str(root),
        "requested": requested,
        "plan": plan,
        "installed_database": str(root / DATABASE_PATH),
        "packages": [
            {
                "name": name,
                "reason": records[name]["install_reason"],
                "identity": records[name]["identity"],
            }
            for name in plan
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Manage v0 prototype")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_install = subparsers.add_parser("install")
    parser_install.add_argument("--repository", type=Path, required=True)
    parser_install.add_argument("--root", type=Path, required=True)
    parser_install.add_argument("package")

    args = parser.parse_args()
    if args.command == "install":
        print(json.dumps(
            install(args.repository, args.root, args.package),
            indent=2,
            sort_keys=True,
        ))


if __name__ == "__main__":
    main()
