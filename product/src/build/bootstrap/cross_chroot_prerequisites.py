"""Verified imported Stage 1A prerequisites for FS-002 selection.

The caller must first validate and restore the Stage 1A handoff. This module
converts that validated provenance into a narrowly checked prerequisite set;
it does not declare dependencies or add another package-selection authority.
"""
from __future__ import annotations

from pathlib import Path
import re


class ImportedPrerequisiteError(ValueError):
    """Stage 1A does not establish a required imported prerequisite."""


_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
_VERSION = re.compile(r"^[0-9][A-Za-z0-9.+_-]*$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def imported_prerequisites(metadata: dict, installed: Path) -> dict[str, str]:
    """Return proven package versions from a validated and restored Stage 1A.

    Provenance alone is not evidence that a tool is available: the cross
    Binutils capability used by GCC is also checked in the restored filesystem.
    Other packages are not declared available merely because their sources
    appear in the handoff; their filesystem contracts must first be defined.
    """
    if not isinstance(metadata, dict):
        raise ImportedPrerequisiteError("Stage 1A metadata must be a mapping")
    toolchain = metadata.get("toolchain")
    if not isinstance(toolchain, dict):
        raise ImportedPrerequisiteError("missing validated toolchain identity")
    target = toolchain.get("target")
    if not isinstance(target, str) or not re.fullmatch(r"[a-zA-Z0-9_.+-]+", target):
        raise ImportedPrerequisiteError("invalid Stage 1A target")
    if (toolchain.get("sysroot"), toolchain.get("tools_prefix")) != (
        "/toolchain", "/toolchain/tools"
    ):
        raise ImportedPrerequisiteError("incompatible Stage 1A mount contract")
    installed = Path(installed)
    if installed.is_symlink() or not installed.is_dir():
        raise ImportedPrerequisiteError("restored root must be a real directory")
    sources = metadata.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ImportedPrerequisiteError("missing Stage 1A source provenance")
    versions: dict[str, str] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise ImportedPrerequisiteError("invalid source provenance entry")
        package, version, digest = (source.get(k) for k in ("package", "version", "sha256"))
        if (not isinstance(package, str) or not _NAME.fullmatch(package)
            or not isinstance(version, str) or not _VERSION.fullmatch(version)
            or not isinstance(digest, str) or not _DIGEST.fullmatch(digest)):
            raise ImportedPrerequisiteError("invalid imported package identity")
        if package in versions and versions[package] != version:
            raise ImportedPrerequisiteError(f"conflicting Stage 1A versions: {package}")
        versions[package] = version

    # The first bounded consumer is GCC's manifest-declared Binutils
    # prerequisite. Verify the cross assembler and linker in the imported root.
    result: dict[str, str] = {}
    if "binutils" in versions:
        for tool in (f"{target}-as", f"{target}-ld"):
            candidate = installed / "tools" / "bin" / tool
            if (not candidate.is_file() or candidate.is_symlink()
                or not candidate.resolve().is_relative_to(installed.resolve())):
                raise ImportedPrerequisiteError(f"imported Binutils tool unavailable: {tool}")
        result["binutils"] = versions["binutils"]
    return result
