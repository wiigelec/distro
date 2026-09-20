#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

EXCLUDED_PAYLOAD_PATHS = {"usr/share/info/dir"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_entries(stage: Path) -> list[tuple[Path, str]]:
    entries = []
    for path in sorted(stage.rglob("*")):
        relative = path.relative_to(stage).as_posix()
        if relative in EXCLUDED_PAYLOAD_PATHS:
            continue
        entries.append((path, relative))
    return entries


def package_metadata(
    *,
    name: str,
    version: str,
    depends: list[dict],
    owned_paths: list[str],
) -> dict:
    return {
        "schema_version": 1,
        "identity": {
            "name": name,
            "version": version,
            "architecture": "x86_64",
            "revision": "r1",
        },
        "depends": depends,
        "conflicts": [],
        "provides": [],
        "owned_paths": owned_paths,
    }


def write_artifact(
    artifact: Path,
    metadata: dict,
    stage: Path | None,
) -> None:
    artifact.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()

    with tarfile.open(artifact, "w:gz") as tar:
        info = tarfile.TarInfo("metadata.json")
        info.size = len(encoded)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(encoded))

        root = tarfile.TarInfo("root")
        root.type = tarfile.DIRTYPE
        root.mode = 0o755
        tar.addfile(root)

        if stage is not None:
            for path, relative in payload_entries(stage):
                tar.add(
                    path,
                    arcname=f"root/{relative}",
                    recursive=False,
                )


def load_repository_records(output_root: Path) -> list[dict]:
    database_path = output_root / "repository" / "database.json"
    if not database_path.is_file():
        raise RuntimeError(
            "incremental package build requires an existing published repository; "
            "run the manifest build once without --pkg"
        )
    database = json.loads(database_path.read_text(encoding="utf-8"))
    if database.get("schema_version") != 1:
        raise RuntimeError("unsupported repository database schema")
    return database.get("packages", [])


def build_record(build: dict, repository: Path) -> dict:
    stage = Path(build["stage_dir"])
    entries = payload_entries(stage)
    owned_paths = [
        relative
        for path, relative in entries
        if path.is_file() or path.is_symlink()
    ]
    metadata = package_metadata(
        name=build["name"],
        version=build["version"],
        depends=[],
        owned_paths=owned_paths,
    )
    artifact_name = (
        f"{build['name']}-{build['version']}-x86_64-r1.distro.tar.gz"
    )
    artifact = repository / artifact_name
    write_artifact(artifact, metadata, stage)
    return {
        **metadata,
        "artifact": artifact_name,
        "artifact_sha256": sha256_file(artifact),
    }


def publish_repository(
    builds: list[dict],
    manifest: dict,
    output_root: Path,
    *,
    incremental: bool = False,
) -> dict:
    repository = output_root / "repository"
    repository.mkdir(parents=True, exist_ok=True)

    selected = {build["name"] for build in builds}
    existing_by_name = {}
    if incremental:
        existing_by_name = {
            record["identity"]["name"]: record
            for record in load_repository_records(output_root)
            if record["identity"]["name"] != manifest["name"]
        }

    retained = {
        name: record
        for name, record in existing_by_name.items()
        if name not in selected
    }

    owners: dict[str, str] = {}
    for name, record in retained.items():
        artifact = repository / record["artifact"]
        if not artifact.is_file():
            raise RuntimeError(f"published artifact missing: {artifact.name}")
        if sha256_file(artifact) != record["artifact_sha256"]:
            raise RuntimeError(f"published artifact checksum mismatch: {artifact.name}")
        for owned in record.get("owned_paths", []):
            previous = owners.get(owned)
            if previous is not None and previous != name:
                raise RuntimeError(
                    f"payload ownership collision: {owned}: {previous} and {name}"
                )
            owners[owned] = name

    new_records = {}
    for build in builds:
        record = build_record(build, repository)
        name = build["name"]
        for owned in record["owned_paths"]:
            previous = owners.get(owned)
            if previous is not None and previous != name:
                raise RuntimeError(
                    f"payload ownership collision: {owned}: {previous} and {name}"
                )
            owners[owned] = name
        old = existing_by_name.get(name)
        if old is not None and old["artifact"] != record["artifact"]:
            old_artifact = repository / old["artifact"]
            if old_artifact.is_file():
                old_artifact.unlink()
        new_records[name] = record

    package_records = []
    for package in manifest["packages"]:
        name = package["name"]
        record = new_records.get(name) or retained.get(name)
        if record is None:
            raise RuntimeError(
                f"repository is missing manifest package {name}; "
                "run a full manifest build first"
            )
        package_records.append(record)

    meta_name = manifest["name"]
    meta_metadata = package_metadata(
        name=meta_name,
        version="1",
        depends=[{"name": package["name"]} for package in manifest["packages"]],
        owned_paths=[],
    )
    meta_artifact_name = f"{meta_name}-1-x86_64-r1.distro.tar.gz"
    meta_artifact = repository / meta_artifact_name
    write_artifact(meta_artifact, meta_metadata, None)
    meta_record = {
        **meta_metadata,
        "artifact": meta_artifact_name,
        "artifact_sha256": sha256_file(meta_artifact),
    }

    records = package_records + [meta_record]
    database = {
        "schema_version": 1,
        "packages": records,
    }
    database_path = repository / "database.json"
    database_path.write_text(
        json.dumps(database, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return {
        "repository": str(repository),
        "database": str(database_path),
        "incremental": incremental,
        "updated_packages": sorted(selected),
        "packages": [
            {
                "name": record["identity"]["name"],
                "version": record["identity"]["version"],
                "artifact": record["artifact"],
                "artifact_sha256": record["artifact_sha256"],
                "owned_path_count": len(record["owned_paths"]),
                "depends": record["depends"],
            }
            for record in records
        ],
    }
