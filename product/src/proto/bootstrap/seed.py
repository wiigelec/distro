#!/usr/bin/env python3
"""Create the explicit Stage-0 Distro seed repository on an Arch host."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path


BOOTSTRAP_VERSION = "1.0.0"
BOOTSTRAP_PACKAGES = (
    "filesystem",
    "bash",
    "coreutils",
    "findutils",
    "grep",
    "sed",
    "gawk",
    "tar",
    "gzip",
    "bzip2",
    "xz",
    "python",
    "gcc",
    "make",
    "binutils",
    "musl",
    "kernel-headers-musl",
    "linux",
    "util-linux",
    "e2fsprogs",
    "syslinux",
    "libisoburn",
    "cpio",
    "ca-certificates",
)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def architecture():
    machine = platform.machine().lower()
    if machine not in {"x86_64", "amd64"}:
        raise RuntimeError("Stage-0 prototype currently supports x86_64 only")
    return "x86_64"


def repository_root():
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "product/src/proto/manager/manage.py").is_file():
            return parent
    raise RuntimeError("unable to locate distro repository root")


def require_root():
    if os.geteuid() != 0:
        raise RuntimeError("Stage-0 seed creation must run as root")


def require_tool(name):
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"required Stage-0 host tool is missing: {name}")
    return path


def tar_add_tree(tar, stage):
    """Add a root tree without hardlink/special-file archive members."""
    for path in sorted(stage.rglob("*")):
        relative = path.relative_to(stage).as_posix()
        archive_name = f"root/{relative}"
        st = path.lstat()

        info = tarfile.TarInfo(archive_name)
        info.mode = stat.S_IMODE(st.st_mode)
        info.uid = 0
        info.gid = 0
        info.mtime = 0

        if stat.S_ISLNK(st.st_mode):
            info.type = tarfile.SYMTYPE
            info.linkname = os.readlink(path)
            tar.addfile(info)
        elif stat.S_ISDIR(st.st_mode):
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
        elif stat.S_ISREG(st.st_mode):
            info.type = tarfile.REGTYPE
            info.size = st.st_size
            with path.open("rb") as handle:
                tar.addfile(info, handle)
        else:
            # Runtime pseudo-filesystems/devices are substrate, not package payload.
            continue


def payload_paths(stage):
    paths = []
    for path in sorted(stage.rglob("*")):
        st = path.lstat()
        if stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
            paths.append(path.relative_to(stage).as_posix())
    return paths


def create_artifact(repository, name, version, stage, extra_metadata=None):
    identity = {
        "name": name,
        "version": version,
        "architecture": architecture(),
        "revision": "r1",
    }
    filename = f"{name}-{version}-{identity['architecture']}-r1.distro.tar.gz"
    artifact = repository / "packages" / filename
    owned_paths = payload_paths(stage)

    metadata = {
        "schema_version": 1,
        "prototype": True,
        "identity": identity,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    with tarfile.open(artifact, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        payload = json.dumps(metadata, indent=2, sort_keys=True).encode() + b"\n"
        info = tarfile.TarInfo("metadata.json")
        info.mode = 0o644
        info.uid = 0
        info.gid = 0
        info.mtime = 0
        info.size = len(payload)
        import io
        tar.addfile(info, io.BytesIO(payload))

        root_info = tarfile.TarInfo("root")
        root_info.type = tarfile.DIRTYPE
        root_info.mode = 0o755
        root_info.uid = 0
        root_info.gid = 0
        root_info.mtime = 0
        tar.addfile(root_info)
        tar_add_tree(tar, stage)

    return {
        "identity": identity,
        "artifact": f"packages/{filename}",
        "artifact_sha256": sha256_file(artifact),
        "owned_paths": owned_paths,
    }


def create_empty_artifact(repository, name, version):
    with tempfile.TemporaryDirectory(prefix="distro-empty-package-") as temporary:
        return create_artifact(
            repository,
            name,
            version,
            Path(temporary),
            {"stage0": True},
        )


def build_seed(output):
    require_root()
    pacstrap = require_tool("pacstrap")
    repo_root = repository_root()

    output = output.resolve()
    if output.exists():
        shutil.rmtree(output)
    (output / "packages").mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="distro-stage0-") as temporary:
        stage = Path(temporary) / "root"
        stage.mkdir()

        subprocess.run(
            [pacstrap, "-c", str(stage), *BOOTSTRAP_PACKAGES],
            check=True,
        )

        # Remove mutable/download caches from the immutable seed payload.
        shutil.rmtree(stage / "var/cache/pacman/pkg", ignore_errors=True)
        (stage / "var/cache/pacman/pkg").mkdir(parents=True, exist_ok=True)
        for log in (stage / "var/log").glob("*"):
            if log.is_file():
                log.unlink()

        # The prototype implementation itself becomes package-owned at the
        # Stage-0 boundary. Nothing is copied from the host into later roots.
        proto_destination = stage / "opt/distro/proto"
        proto_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            repo_root / "product/src/proto",
            proto_destination,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

        bootstrap = create_artifact(
            output,
            "bootstrap-tools",
            BOOTSTRAP_VERSION,
            stage,
            {
                "stage0": True,
                "stage0_origin": "arch-pacstrap",
                "stage0_packages": list(BOOTSTRAP_PACKAGES),
            },
        )

    build_system = create_empty_artifact(output, "build-system", "1.0.0")

    database = {
        "schema_version": 1,
        "prototype": True,
        "architecture": architecture(),
        "stage0": True,
        "packages": [
            {
                **bootstrap,
                "depends": [],
                "conflicts": [],
                "provides": [{"name": "bootstrap-tools"}],
            },
            {
                **build_system,
                "depends": [{"name": "bootstrap-tools"}],
                "conflicts": [],
                "provides": [{"name": "build-system"}],
            },
        ],
    }
    write_json(output / "database.json", database)

    result = {
        "schema_version": 1,
        "status": "success",
        "stage0": True,
        "repository": str(output),
        "bootstrap_packages": list(BOOTSTRAP_PACKAGES),
        "artifact": str(output / bootstrap["artifact"]),
        "artifact_sha256": bootstrap["artifact_sha256"],
        "owned_path_count": len(bootstrap["owned_paths"]),
        "trust_boundary": (
            "Host package content is permitted only in this Stage-0 seed. "
            "Accepted build and ISO roots below this boundary are assembled "
            "only by Manage from Distro artifacts."
        ),
    }
    write_json(output / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Create the explicit Distro Stage-0 seed repository"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/distro-seed-repo"),
    )
    args = parser.parse_args()
    print(json.dumps(build_seed(args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
