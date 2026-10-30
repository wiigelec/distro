"""Versioned Stage 1A handoff metadata and integrity checks."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

SCHEMA_VERSION = 1
ARCHIVE_NAME = "cross-toolchain.tar.xz"
METADATA_NAME = "cross-toolchain.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_revision() -> dict:
    """Never claim a clean source revision unless Git confirms it."""
    repository = Path(__file__).resolve().parents[4]
    try:
        rev = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"],
                             check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        status = subprocess.run(["git", "-C", str(repository), "status", "--porcelain", "--untracked-files=all"],
                                check=True, capture_output=True, text=True, timeout=10).stdout
        if not re.fullmatch(r"[0-9a-f]{40,64}", rev):
            raise ValueError("invalid revision")
        return {"revision": rev, "working_tree_clean": not bool(status.strip())}
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return {"revision": None, "working_tree_clean": None}


def make_metadata(archive: Path, steps, *, target: str, host_triplet: str,
                  duration_seconds: float) -> dict:
    """Derive provenance from the validated package selection."""
    if not Path(archive).is_file():
        raise ValueError("candidate archive missing")
    sources = [{
        "step": step.id, "package": step.name, "version": step.version,
        "sha256": step.checksum, "recipe": step.recipe.name,
        "supplements": [
            {"package": identity, "version": version, "sha256": checksum}
            for identity, (version, checksum) in sorted(step.supplements.items())
        ],
    } for step in steps]
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": {
            "type": "cross-toolchain", "stage": "1A", "filename": ARCHIVE_NAME,
            "format": "tar.xz", "sha256": sha256_file(archive),
            "size_bytes": Path(archive).stat().st_size,
        },
        "toolchain": {
            "target": target, "sysroot": "/toolchain", "tools_prefix": "/toolchain/tools",
        },
        "build": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration_seconds, 3),
            "host_triplet": host_triplet,
            **repository_revision(),
        },
        "sources": sources,
        "verification": {"functional": "passed", "relocation": "passed"},
    }


def validate_handoff(archive: Path, metadata: dict) -> None:
    """Reject incompatible, incomplete, or corrupt candidate handoffs."""
    if not isinstance(metadata, dict) or metadata.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported handoff schema")
    a, t = metadata.get("artifact"), metadata.get("toolchain")
    if not isinstance(a, dict) or not isinstance(t, dict):
        raise ValueError("invalid handoff metadata")
    if (a.get("type"), a.get("stage"), a.get("filename"), a.get("format")) != (
            "cross-toolchain", "1A", ARCHIVE_NAME, "tar.xz"):
        raise ValueError("incorrect artifact identity")
    if (t.get("sysroot"), t.get("tools_prefix")) != ("/toolchain", "/toolchain/tools"):
        raise ValueError("incorrect mount contract")
    if not isinstance(t.get("target"), str) or not t["target"]:
        raise ValueError("missing target")
    if not isinstance(metadata.get("sources"), list) or not metadata["sources"]:
        raise ValueError("missing source provenance")
    # Validate schema rather than merely requiring a nonempty provenance array.
    seen_steps = set()
    for source in metadata["sources"]:
        if not isinstance(source, dict):
            raise ValueError("source provenance entry must be an object")
        if set(source) != {"step", "package", "version", "sha256", "recipe", "supplements"}:
            raise ValueError("source provenance entry has missing or unknown fields")
        if not all(isinstance(source[k], str) and source[k] for k in ("step", "package", "version", "recipe")):
            raise ValueError("invalid source identity")
        if source["step"] in seen_steps:
            raise ValueError("duplicate source step identity")
        seen_steps.add(source["step"])
        if not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
            raise ValueError("invalid source digest")
        if not source["recipe"].endswith(".sh") or "/" in source["recipe"] or "\\" in source["recipe"]:
            raise ValueError("invalid source recipe basename")
        if not isinstance(source["supplements"], list):
            raise ValueError("supplements must be a list")
        identities = set()
        for supplement in source["supplements"]:
            if not isinstance(supplement, dict) or set(supplement) != {"package", "version", "sha256"}:
                raise ValueError("invalid supplementary provenance fields")
            if not all(isinstance(supplement[k], str) and supplement[k] for k in ("package", "version")):
                raise ValueError("invalid supplementary identity")
            if supplement["package"] in identities:
                raise ValueError("duplicate supplementary source identity")
            identities.add(supplement["package"])
            if not re.fullmatch(r"[0-9a-f]{64}", supplement["sha256"]):
                raise ValueError("invalid supplementary source digest")
    if metadata.get("verification") != {"functional": "passed", "relocation": "passed"}:
        raise ValueError("verification is incomplete")
    archive = Path(archive)
    if archive.name != ARCHIVE_NAME or not archive.is_file() or archive.is_symlink():
        raise ValueError("archive missing or invalid")
    if a.get("size_bytes") != archive.stat().st_size:
        raise ValueError("archive size mismatch")
    if a.get("sha256") != sha256_file(archive):
        raise ValueError("archive SHA-256 mismatch")


def validate_published_handoff(artifacts: Path) -> dict:
    """A valid metadata file is the completion marker for the archive pair."""
    artifacts = Path(artifacts)
    path = artifacts / METADATA_NAME
    if path.is_symlink() or not path.is_file():
        raise ValueError("handoff metadata missing or invalid")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    validate_handoff(artifacts / ARCHIVE_NAME, metadata)
    return metadata
