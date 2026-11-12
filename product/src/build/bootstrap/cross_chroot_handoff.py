"""Stage 1C filesystem handoff: validated, metadata-last publication.

Only an already independently restored and native-verified FS-002 candidate
may become a complete cross-chroot handoff. The completion marker is metadata.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from build.bootstrap.cross_toolchain import _validate_candidate_archive
from build.bootstrap.cross_toolchain_metadata import sha256_file, repository_revision
from build.selection import SelectionError

ARCHIVE_NAME = "cross-chroot.tar.xz"
METADATA_NAME = "cross-chroot.json"


def _sources(steps):
    return [{
        "step": step.id, "package": step.name, "version": step.version,
        "sha256": step.checksum, "recipe": step.recipe.name,
        "supplements": [
            {"package": key, "version": ver, "sha256": sha}
            for key, (ver, sha) in sorted(step.supplements.items())
        ],
    } for step in steps]


def validate_cross_chroot_handoff(archive: Path, metadata: dict) -> None:
    """Reject a partial, foreign, corrupted or nonverified Stage 1C handoff."""
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        raise SelectionError("invalid Stage 1C handoff schema")
    artifact = metadata.get("artifact")
    parent = metadata.get("parent_stage_1a")
    if not isinstance(artifact, dict) or not isinstance(parent, dict):
        raise SelectionError("missing Stage 1C artifact or parent provenance")
    if (artifact.get("type"), artifact.get("stage"), artifact.get("filename"),
            artifact.get("format")) != ("cross-chroot", "1B", ARCHIVE_NAME, "tar.xz"):
        raise SelectionError("invalid Stage 1C artifact identity")
    if not re.fullmatch(r"[0-9a-f]{64}", str(parent.get("sha256", ""))):
        raise SelectionError("invalid parent Stage 1A digest")
    if parent.get("filename") != "cross-toolchain.tar.xz":
        raise SelectionError("incorrect parent Stage 1A identity")
    target = metadata.get("toolchain", {})
    if target.get("target") != "x86_64-distro-linux-gnu" or target.get("runtime_root") != "/":
        raise SelectionError("invalid Stage 1C target mount contract")
    selections = metadata.get("sources")
    if not isinstance(selections, list) or not selections:
        raise SelectionError("missing Stage 1C source selection provenance")
    seen = set()
    for source in selections:
        if not isinstance(source, dict) or set(source) != {
            "step", "package", "version", "sha256", "recipe", "supplements"
        }:
            raise SelectionError("invalid Stage 1C source record")
        if not all(isinstance(source[k], str) and source[k]
                   for k in ("step", "package", "version", "recipe")):
            raise SelectionError("invalid Stage 1C source identity")
        if source["step"] in seen:
            raise SelectionError("duplicate Stage 1C source selection")
        seen.add(source["step"])
        if not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
            raise SelectionError("invalid source fingerprint")
        if not source["recipe"].endswith(".sh") or "/" in source["recipe"] or "\\" in source["recipe"]:
            raise SelectionError("invalid recipe basename")
        if not isinstance(source["supplements"], list):
            raise SelectionError("invalid supplemental provenance")
        for supplement in source["supplements"]:
            if not isinstance(supplement, dict) or set(supplement) != {"package", "version", "sha256"}:
                raise SelectionError("invalid supplement")
            if not all(isinstance(supplement[k], str) and supplement[k]
                       for k in ("package", "version")) or not re.fullmatch(
                    r"[0-9a-f]{64}", str(supplement["sha256"])):
                raise SelectionError("invalid supplemental fingerprint")
    if [s["step"] for s in selections[-2:]] != ["native-binutils", "native-gcc"]:
        raise SelectionError("incomplete native toolchain selection")
    verification = metadata.get("verification")
    if not isinstance(verification, dict) or verification.get("functional") != "passed" or \
            verification.get("relocation") != "passed" or verification.get("elf_dependencies") != "passed":
        raise SelectionError("Stage 1C verification incomplete")
    graph = verification.get("dependency_graph_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", str(graph)):
        raise SelectionError("invalid dependency graph identity")
    archive = Path(archive)
    if archive.name != ARCHIVE_NAME or archive.is_symlink() or not archive.is_file():
        raise SelectionError("missing regular Stage 1C archive")
    if artifact.get("size_bytes") != archive.stat().st_size or artifact.get("sha256") != sha256_file(archive):
        raise SelectionError("Stage 1C archive digest/size mismatch")
    _validate_candidate_archive(archive)


def validate_published_cross_chroot(artifacts: Path) -> dict:
    artifacts = Path(artifacts)
    path = artifacts / METADATA_NAME
    if path.is_symlink() or not path.is_file():
        raise SelectionError("Stage 1C completion marker missing")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    validate_cross_chroot_handoff(artifacts / ARCHIVE_NAME, metadata)
    return metadata


def publish_cross_chroot(
    workspace: Path, staging: Path, candidate: Path, steps,
    parent_metadata: dict,
) -> Path:
    """Publish preverified relocation archive, with completion metadata last.

    Preconditions are checked again immediately before copying. Every failure
    removes files bearing the final names. Other artifacts are never touched.
    """
    workspace, staging, candidate = map(
        lambda p: Path(p).absolute(), (workspace, staging, candidate)
    )
    if candidate != staging / "native-gcc-candidate-root":
        raise SelectionError("handoff requires the approved native GCC candidate")
    if staging != workspace / "staging" or not candidate.is_dir() or candidate.is_symlink():
        raise SelectionError("invalid handoff workspace")
    functional = json.loads((staging / "native-gcc-functional-verification.json").read_text())
    relocation = json.loads((staging / "native-gcc-relocation-verification.json").read_text())
    graph = functional.get("elf_dependencies", {}).get("dependency_graph_sha256")
    relocated = relocation.get("relocated_smoke", {})
    if (functional.get("success") is not True or relocation.get("success") is not True or
        relocated.get("success") is not True or
        functional.get("elf_dependencies", {}).get("success") is not True or
        relocated.get("elf_dependencies", {}).get("success") is not True or
        not isinstance(graph, str) or len(graph) != 64 or
        relocated.get("elf_dependencies", {}).get("dependency_graph_sha256") != graph or
        relocation.get("independent_restoration") is not True or
        relocation.get("host_userspace_mounted") is not False):
        raise SelectionError("functional, relocation or ELF evidence incomplete")
    parent = parent_metadata.get("artifact", {})
    if parent.get("type") != "cross-toolchain" or parent.get("stage") != "1A" or \
            not re.fullmatch(r"[0-9a-f]{64}", str(parent.get("sha256", ""))):
        raise SelectionError("parent Stage 1A handoff identity missing")
    source_archive = staging / "native-gcc-relocation-candidate.tar.xz"
    if (source_archive.is_symlink() or not source_archive.is_file() or
        source_archive.stat().st_size != relocation.get("archive_size") or
        sha256_file(source_archive) != relocation.get("archive_sha256")):
        raise SelectionError("relocation-verified archive changed")
    _validate_candidate_archive(source_archive)
    artifacts = workspace / "artifacts"
    if artifacts.is_symlink():
        raise SelectionError("artifact destination is a symlink")
    artifacts.mkdir(exist_ok=True)
    if not artifacts.is_dir() or artifacts.resolve() != artifacts:
        raise SelectionError("artifact destination is not a real directory")
    final_archive = artifacts / ARCHIVE_NAME
    final_metadata = artifacts / METADATA_NAME
    if any(p.exists() or p.is_symlink() for p in (final_archive, final_metadata)):
        raise SelectionError("Stage 1C handoff already exists; refusing replacement")
    metadata = {
        "schema_version": 1,
        "artifact": {
            "type": "cross-chroot", "stage": "1B", "filename": ARCHIVE_NAME,
            "format": "tar.xz", "sha256": relocation["archive_sha256"],
            "size_bytes": relocation["archive_size"],
        },
        "parent_stage_1a": {"filename": "cross-toolchain.tar.xz", "sha256": parent["sha256"]},
        "toolchain": {"target": "x86_64-distro-linux-gnu", "runtime_root": "/"},
        "sources": _sources(steps),
        "verification": {
            "functional": "passed", "relocation": "passed", "elf_dependencies": "passed",
            "dependency_graph_sha256": graph,
        },
        "build": {"created_utc": datetime.now(timezone.utc).isoformat(), **repository_revision()},
    }
    # Temporary files are confined to artifact destination for atomic renames.
    # Publish the metadata LAST so no partial handoff is accepted as complete.
    with tempfile.TemporaryDirectory(dir=artifacts, prefix="handoff-") as tempdir:
        temp_archive = Path(tempdir) / ARCHIVE_NAME
        temp_metadata = Path(tempdir) / METADATA_NAME
        shutil.copyfile(source_archive, temp_archive)
        validate_cross_chroot_handoff(temp_archive, metadata)
        temp_metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            temp_archive.replace(final_archive)
            temp_metadata.replace(final_metadata)
            validate_published_cross_chroot(artifacts)
        except Exception:
            final_metadata.unlink(missing_ok=True)
            final_archive.unlink(missing_ok=True)
            raise
    return final_archive
