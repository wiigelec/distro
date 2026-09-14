#!/usr/bin/env python3
"""Verify prototype package archives and completed build results."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import tarfile
from pathlib import Path, PurePosixPath


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_member_name(name):
    path = PurePosixPath(name)
    if path.is_absolute():
        return False
    normalized = posixpath.normpath(name)
    return normalized != ".." and not normalized.startswith("../")


def verify_artifact(artifact, expected_metadata=None, expected_sha256=None):
    artifact = Path(artifact)
    if not artifact.is_file():
        raise RuntimeError(f"package artifact does not exist: {artifact}")

    actual_sha256 = sha256_file(artifact)
    if expected_sha256 and actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"artifact SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    with tarfile.open(artifact, "r:gz") as tar:
        members = tar.getmembers()
        names = {member.name for member in members}

        for member in members:
            if not safe_member_name(member.name):
                raise RuntimeError(f"unsafe package member path: {member.name}")

        if "metadata.json" not in names:
            raise RuntimeError("package is missing metadata.json")
        if "root/usr/bin/curl" not in names:
            raise RuntimeError("curl package is missing root/usr/bin/curl")

        metadata_file = tar.extractfile("metadata.json")
        if metadata_file is None:
            raise RuntimeError("metadata.json is not a regular readable archive member")
        metadata = json.load(metadata_file)

    if expected_metadata is not None and metadata != expected_metadata:
        raise RuntimeError("embedded package metadata does not match build metadata")

    return {
        "status": "success",
        "artifact_sha256": actual_sha256,
        "member_count": len(members),
        "required_members": [
            "metadata.json",
            "root/usr/bin/curl",
        ],
        "metadata": metadata,
    }


def verify_result(result_path):
    result_path = Path(result_path)
    result = json.loads(result_path.read_text())

    if result.get("status") != "success":
        raise RuntimeError(f"build result is not successful: {result.get('status')}")

    identity = result.get("identity", {})
    if identity.get("name") != "curl":
        raise RuntimeError("acceptance fixture expected package name curl")
    if identity.get("revision") != "r1":
        raise RuntimeError("acceptance fixture expected revision r1")
    if identity.get("architecture") not in {"x86_64", "aarch64"}:
        raise RuntimeError(
            f"unexpected architecture for curl fixture: {identity.get('architecture')}"
        )

    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        raise RuntimeError("result is missing package metadata")
    if metadata.get("identity") != identity:
        raise RuntimeError("result identity does not match embedded metadata identity")
    if metadata.get("build_system") != "cmake":
        raise RuntimeError("curl acceptance fixture expected cmake build system")
    if metadata.get("install_prefix") != "/usr":
        raise RuntimeError("curl acceptance fixture expected /usr install prefix")

    artifact = Path(result["artifact"])
    verification = verify_artifact(
        artifact,
        expected_metadata=metadata,
        expected_sha256=result.get("artifact_sha256"),
    )

    if result.get("source_sha256") != metadata.get("source", {}).get("sha256"):
        raise RuntimeError("source SHA-256 differs between result and package metadata")
    if result.get("recipe_sha256") != metadata.get("recipe_sha256"):
        raise RuntimeError("recipe SHA-256 differs between result and package metadata")

    return {
        "status": "success",
        "result": str(result_path),
        "identity": identity,
        "artifact": str(artifact),
        "artifact_sha256": verification["artifact_sha256"],
        "member_count": verification["member_count"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--result",
        action="store_true",
        help="treat path as a completed result.json instead of a package artifact",
    )
    args = parser.parse_args()

    if args.result:
        verified = verify_result(args.path)
    else:
        verified = verify_artifact(args.path)

    print(json.dumps(verified, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
