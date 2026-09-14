#!/usr/bin/env python3
"""End-to-end prototype: discover -> recipe -> clean build -> package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

from discover import discover, load_manifest
from recipe import generate_recipe
from verify import verify_artifact


USER_AGENT = "distro-builder-prototype/0"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def download(url, destination):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def safe_extract(archive, destination):
    root = destination.resolve()

    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"archive member escapes extraction root: {member.name}")
            if member.issym() or member.islnk():
                raise RuntimeError(f"prototype rejects archive links: {member.name}")
        tar.extractall(destination)

    children = [path for path in destination.iterdir()]
    directories = [path for path in children if path.is_dir()]
    if len(children) != 1 or len(directories) != 1:
        raise RuntimeError("expected GitHub source archive to contain one top-level directory")
    return directories[0]


def container_backend():
    for executable in ("podman", "docker"):
        path = shutil.which(executable)
        if path:
            return executable, path
    raise RuntimeError("clean build requires podman or docker on PATH")


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def build_in_container(workspace, recipe, log_path):
    backend_name, backend = container_backend()
    packages = " ".join(shell_quote(item) for item in recipe["environment"]["packages"])
    commands = [item["command"] for item in recipe["build"]["commands"]]

    shell_lines = [
        "set -eux",
        "export DEBIAN_FRONTEND=noninteractive",
        "apt-get update",
        f"apt-get install -y --no-install-recommends {packages}",
        *commands,
        "test -x /work/stage/usr/bin/curl",
    ]

    # Rootless Podman maps container root to the invoking host user. Chowning
    # /work to the numeric host UID from inside that user namespace instead
    # maps ownership to a subordinate host UID and makes the workspace
    # inaccessible after the container exits. Rootful Docker needs the
    # explicit ownership handoff.
    if backend_name == "docker":
        shell_lines.append('chown -R "$HOST_UID:$HOST_GID" /work')

    shell = "\n".join(shell_lines)

    volume = f"{workspace.resolve()}:/work"
    if backend_name == "podman":
        volume += ":Z"

    command = [
        backend,
        "run",
        "--rm",
    ]
    if backend_name == "docker":
        command.extend([
            "--env", f"HOST_UID={os.getuid()}",
            "--env", f"HOST_GID={os.getgid()}",
        ])

    command.extend([
        "--volume", volume,
        recipe["environment"]["image"],
        "/bin/sh",
        "-c",
        shell,
    ])

    with log_path.open("w") as log:
        process = subprocess.run(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

    if process.returncode != 0:
        raise RuntimeError(
            f"{backend_name} build failed with exit code {process.returncode}; "
            f"see {log_path}"
        )

    return backend_name


def package_artifact(workspace, recipe, source_sha256, recipe_sha256):
    packages_dir = workspace / "packages"
    packages_dir.mkdir(exist_ok=True)

    identity = recipe["identity"]
    filename = (
        f"{identity['name']}-{identity['version']}-"
        f"{identity['architecture']}-{identity['revision']}.distro.tar.gz"
    )
    artifact = packages_dir / filename

    metadata = {
        "schema_version": 1,
        "prototype": True,
        "identity": identity,
        "source": {
            "repository": recipe["source"]["repository"],
            "ref": recipe["source"]["ref"],
            "sha256": source_sha256,
        },
        "recipe_sha256": recipe_sha256,
        "build_system": recipe["build"]["system"],
        "install_prefix": recipe["package"]["install_prefix"],
    }

    with tempfile.TemporaryDirectory(prefix="distro-package-") as temporary:
        root = Path(temporary)
        write_json(root / "metadata.json", metadata)
        shutil.copytree(workspace / "stage", root / "root")

        with tarfile.open(artifact, "w:gz") as tar:
            tar.add(root / "metadata.json", arcname="metadata.json")
            tar.add(root / "root", arcname="root")

    return artifact, metadata


def run_package(package, output_root):
    started = int(time.time())

    package_root = output_root / package["name"]
    if package_root.exists():
        shutil.rmtree(package_root)
    package_root.mkdir(parents=True)

    discovery = discover(package)
    write_json(package_root / "discovery.json", discovery)

    recipe = generate_recipe(discovery)
    recipe_path = package_root / "recipe.json"
    write_json(recipe_path, recipe)

    source_archive = package_root / "source.tar.gz"
    download(recipe["source"]["archive_url"], source_archive)
    source_sha256 = sha256_file(source_archive)
    recipe["source"]["sha256"] = source_sha256
    write_json(recipe_path, recipe)

    unpack = package_root / "source-unpack"
    unpack.mkdir()
    extracted = safe_extract(source_archive, unpack)
    shutil.move(str(extracted), str(package_root / "src"))
    shutil.rmtree(unpack)

    (package_root / "build").mkdir()
    (package_root / "stage").mkdir()

    recipe_sha256 = sha256_json(recipe)
    log_path = package_root / "build.log"
    backend = build_in_container(package_root, recipe, log_path)

    artifact, metadata = package_artifact(
        package_root,
        recipe,
        source_sha256,
        recipe_sha256,
    )
    artifact_sha256 = sha256_file(artifact)
    verification = verify_artifact(
        artifact,
        expected_metadata=metadata,
        expected_sha256=artifact_sha256,
    )

    result = {
        "schema_version": 1,
        "status": "success",
        "prototype": True,
        "identity": recipe["identity"],
        "environment": {
            "backend": backend,
            "image": recipe["environment"]["image"],
            "packages": recipe["environment"]["packages"],
        },
        "source_sha256": source_sha256,
        "recipe_sha256": recipe_sha256,
        "artifact": str(artifact),
        "artifact_sha256": artifact_sha256,
        "metadata": metadata,
        "verification": verification,
        "build_log": str(log_path),
        "started_unix": started,
        "finished_unix": int(time.time()),
    }
    write_json(package_root / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Prototype autonomous package discovery/build/package pipeline"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/distro-builder"),
        help="prototype workspace/output root",
    )
    args = parser.parse_args()

    packages = load_manifest(args.manifest)
    args.output.mkdir(parents=True, exist_ok=True)

    results = []
    for package in packages:
        print(f"==> {package['name']}: discover")
        try:
            result = run_package(package, args.output)
        except Exception as exc:
            failure = {
                "schema_version": 1,
                "status": "failure",
                "package": package["name"],
                "error": str(exc),
            }
            package_root = args.output / package["name"]
            package_root.mkdir(parents=True, exist_ok=True)
            write_json(package_root / "result.json", failure)
            raise
        else:
            results.append(result)
            print(f"==> {package['name']}: {result['artifact']}")
            print(f"    sha256 {result['artifact_sha256']}")

    write_json(args.output / "result.json", {"packages": results})


if __name__ == "__main__":
    main()
