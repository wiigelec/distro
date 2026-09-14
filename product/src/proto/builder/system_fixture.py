#!/usr/bin/env python3
"""Build a minimal musl + BusyBox prototype repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path


MUSL_VERSION = "1.2.3"
BUSYBOX_VERSION = "1.37.0"
IMAGE = "debian:12-slim"
USER_AGENT = "distro-system-fixture/0"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, destination):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def container_backend():
    for executable in ("podman", "docker"):
        path = shutil.which(executable)
        if path:
            return executable, path
    raise RuntimeError("system fixture build requires podman or docker on PATH")


def architecture():
    machine = platform.machine().lower()
    if machine not in {"x86_64", "amd64"}:
        raise RuntimeError("system fixture prototype currently supports x86_64 only")
    return "x86_64"


def build_sources(workspace):
    backend_name, backend = container_backend()
    musl_archive = workspace / f"musl-{MUSL_VERSION}.tar.gz"
    busybox_archive = workspace / f"busybox-{BUSYBOX_VERSION}.tar.bz2"

    download(
        f"https://musl.libc.org/releases/musl-{MUSL_VERSION}.tar.gz",
        musl_archive,
    )
    download(
        f"https://busybox.net/downloads/busybox-{BUSYBOX_VERSION}.tar.bz2",
        busybox_archive,
    )

    shell = f'''
set -eux
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends build-essential musl-tools linux-musl-dev bzip2 ca-certificates

mkdir -p /work/src /work/musl-stage /work/busybox-stage

tar -xzf /work/musl-{MUSL_VERSION}.tar.gz -C /work/src
cd /work/src/musl-{MUSL_VERSION}
./configure --prefix=/usr
make -j"$(nproc)"
DESTDIR=/work/musl-stage make install
test -L /work/musl-stage/lib/ld-musl-x86_64.so.1
test -e /work/musl-stage/usr/lib/libc.so

tar -xjf /work/busybox-{BUSYBOX_VERSION}.tar.bz2 -C /work/src
cd /work/src/busybox-{BUSYBOX_VERSION}
make defconfig
sed -i 's/^CONFIG_TC=y/# CONFIG_TC is not set/' .config
yes '' | make oldconfig
make CC=musl-gcc -j"$(nproc)"
make CC=musl-gcc CONFIG_PREFIX=/work/busybox-stage install
test -x /work/busybox-stage/bin/busybox
test -e /work/busybox-stage/bin/sh
test -e /work/busybox-stage/bin/ls
readelf -l /work/busybox-stage/bin/busybox | grep -F '/lib/ld-musl-x86_64.so.1'
'''

    volume = f"{workspace.resolve()}:/work"
    if backend_name == "podman":
        volume += ":Z"

    command = [
        backend, "run", "--rm",
        "--volume", volume,
        IMAGE,
        "/bin/sh", "-c", shell,
    ]

    log_path = workspace.parent / "build.log"
    with log_path.open("w") as log:
        process = subprocess.run(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if process.returncode != 0:
        raise RuntimeError(
            f"{backend_name} system fixture build failed with exit code "
            f"{process.returncode}; see {log_path}"
        )

    return {
        "backend": backend_name,
        "image": IMAGE,
        "musl_source_sha256": sha256_file(musl_archive),
        "busybox_source_sha256": sha256_file(busybox_archive),
        "build_log": str(log_path),
    }


def payload_paths(stage):
    paths = []
    for path in sorted(stage.rglob("*")):
        if path.is_file() or path.is_symlink():
            paths.append(path.relative_to(stage).as_posix())
    return paths


def create_artifact(repository, name, version, stage):
    identity = {
        "name": name,
        "version": version,
        "architecture": architecture(),
        "revision": "r1",
    }
    filename = f"{name}-{version}-{identity['architecture']}-r1.distro.tar.gz"
    artifact = repository / "packages" / filename
    owned_paths = payload_paths(stage)

    with tempfile.TemporaryDirectory(prefix="distro-system-package-") as temporary:
        root = Path(temporary)
        write_json(
            root / "metadata.json",
            {"schema_version": 1, "prototype": True, "identity": identity},
        )
        shutil.copytree(stage, root / "root", symlinks=True)
        with tarfile.open(artifact, "w:gz", dereference=False) as tar:
            tar.add(root / "metadata.json", arcname="metadata.json")
            tar.add(root / "root", arcname="root", recursive=True)

    return {
        "identity": identity,
        "artifact": f"packages/{filename}",
        "artifact_sha256": sha256_file(artifact),
        "owned_paths": owned_paths,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Build musl + BusyBox prototype package repository"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/distro-system-repo"),
    )
    args = parser.parse_args()

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    (output / "packages").mkdir(parents=True)

    workspace = output / "work"
    workspace.mkdir()
    build_info = build_sources(workspace)

    musl = create_artifact(
        output, "musl", MUSL_VERSION, workspace / "musl-stage"
    )
    busybox = create_artifact(
        output, "busybox", BUSYBOX_VERSION, workspace / "busybox-stage"
    )

    database = {
        "schema_version": 1,
        "prototype": True,
        "architecture": architecture(),
        "packages": [
            {
                **musl,
                "depends": [],
                "conflicts": [],
                "provides": [{"name": "libc"}],
            },
            {
                **busybox,
                "depends": [{"name": "musl"}],
                "conflicts": [],
                "provides": [],
            },
        ],
    }
    write_json(output / "database.json", database)

    result = {
        "schema_version": 1,
        "status": "success",
        "repository": str(output),
        "database": str(output / "database.json"),
        "packages": {
            "musl": {
                "artifact": str(output / musl["artifact"]),
                "artifact_sha256": musl["artifact_sha256"],
                "owned_path_count": len(musl["owned_paths"]),
            },
            "busybox": {
                "artifact": str(output / busybox["artifact"]),
                "artifact_sha256": busybox["artifact_sha256"],
                "owned_path_count": len(busybox["owned_paths"]),
            },
        },
        "build": build_info,
    }
    write_json(output / "result.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
