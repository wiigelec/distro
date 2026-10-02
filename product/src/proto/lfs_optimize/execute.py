#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import shlex
import subprocess
import tarfile
import tempfile
import urllib.request
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

from artifact import (
    create_tar_xz,
    delta,
    extract_tar_xz,
    materialize_delta,
    sha256_file,
    snapshot,
    snapshot_digest,
)
from resolve import HERE, resolve

USER_AGENT = "distro-lfs-optimize-prototype/0"
CACHE_SCHEMA_VERSION = 4


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def cached_download(item: dict[str, Any], cache_root: Path) -> Path:
    expected = item["md5"]
    suffix = Path(item["url"]).name
    path = cache_root / "sources" / f"{expected}-{suffix}"
    if not path.is_file():
        download(item["url"], path)
    actual = md5_file(path)
    if actual != expected:
        path.unlink(missing_ok=True)
        raise RuntimeError(
            f"source checksum mismatch for {item['url']}: {actual} != {expected}"
        )
    return path


def safe_extract_source(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tar:
        try:
            tar.extractall(destination, filter="data")
        except TypeError:
            root = destination.resolve()
            for member in tar.getmembers():
                target = (destination / member.name).resolve()
                if target != root and root not in target.parents:
                    raise RuntimeError(
                        f"source archive member escapes extraction root: {member.name}"
                    )
            tar.extractall(destination)
    children = [p for p in destination.iterdir() if p.is_dir()]
    if len(children) != 1:
        raise RuntimeError(
            f"expected one source directory in {destination}, found {len(children)}"
        )
    return children[0]


def require_root() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("execution proof requires root for clone/chroot/mount isolation")


def clone_root(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    subprocess.run(
        [
            "cp", "-a", "--reflink=auto", "--one-file-system",
            f"{source.resolve()}/.", str(destination),
        ],
        check=True,
    )


def mount(source: str, target: Path, *, fstype: str | None = None,
          bind: bool = False, options: str | None = None) -> None:
    target.mkdir(parents=True, exist_ok=True)
    argv = ["mount"]
    if bind:
        argv.append("--bind")
    elif fstype:
        argv.extend(["-t", fstype])
    if options:
        argv.extend(["-o", options])
    argv.extend([source, str(target)])
    subprocess.run(argv, check=True)


@contextmanager
def virtual_mounts(root: Path):
    mounted: list[Path] = []
    try:
        mount("/dev", root / "dev", bind=True)
        mounted.append(root / "dev")
        mount(
            "devpts",
            root / "dev/pts",
            fstype="devpts",
            options="gid=5,mode=0620",
        )
        mounted.append(root / "dev/pts")
        mount("proc", root / "proc", fstype="proc")
        mounted.append(root / "proc")
        mount("sysfs", root / "sys", fstype="sysfs")
        mounted.append(root / "sys")
        mount("tmpfs", root / "run", fstype="tmpfs")
        mounted.append(root / "run")
        yield
    finally:
        for target in reversed(mounted):
            subprocess.run(["umount", "-l", str(target)], check=False)


def chroot_command(root: Path, command: dict[str, Any], cwd: str,
                   log, index: int) -> dict[str, Any]:
    user = command["user"]
    env = {
        "HOME": "/root" if user == "root" else f"/home/{user}",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }
    env.update(command.get("environment", {}))
    exports = " ".join(
        f"{key}={shlex.quote(value)}"
        for key, value in env.items()
    )
    shell = f"cd {shlex.quote(cwd)} && export {exports} && {command['command']}"
    argv = ["chroot"]
    if user != "root":
        argv.append(f"--userspec={user}")
    argv.extend([
        str(root.resolve()),
        "/usr/bin/bash", "-o", "pipefail", "-c", shell,
    ])
    log.write(f"\n# command {index} user={user}\n$ {command['command']}\n")
    log.flush()
    completed = subprocess.run(
        argv, stdout=log, stderr=subprocess.STDOUT, text=True
    )
    return {
        "index": index,
        "user": user,
        "command": command["command"],
        "source_command": command.get("source_command"),
        "exit_code": completed.returncode,
    }


def prepare_sources(package: dict[str, Any], clone: Path, cache: Path) -> str:
    name = package["name"]
    version = package["version"]
    host_build_root = clone / "tmp/distro-lfs-optimize" / f"{name}-{version}"
    if host_build_root.exists():
        shutil.rmtree(host_build_root)
    host_build_root.mkdir(parents=True)

    source_archive = cached_download(package["source"], cache)
    extracted = safe_extract_source(source_archive, host_build_root / "unpack")
    host_source = host_build_root / "source"
    extracted.rename(host_source)
    shutil.rmtree(host_build_root / "unpack")

    for resource in package.get("resources", {}).values():
        resource_path = cached_download(resource, cache)
        shutil.copy2(resource_path, host_build_root / Path(resource["url"]).name)

    return f"/tmp/distro-lfs-optimize/{name}-{version}/source"


def resolve_working_directory(source_cwd: str, working_directory: str) -> str:
    if working_directory == "source":
        return source_cwd

    relative = PurePosixPath(working_directory)
    if (
        not working_directory
        or relative.is_absolute()
        or "." in relative.parts
        or ".." in relative.parts
    ):
        raise RuntimeError(
            f"invalid source-relative working directory: {working_directory}"
        )

    return str(PurePosixPath(source_cwd) / relative)


def build_package(package: dict[str, Any], root: Path, work: Path, cache: Path,
                  run_tests: bool, realize_to: Path | None) -> dict[str, Any]:
    require_root()
    root = root.resolve()
    if not (root / "usr/bin/bash").is_file():
        raise RuntimeError(f"{root}: execution root lacks /usr/bin/bash")

    before = snapshot(root)
    base_digest = snapshot_digest(before)
    definition_digest = canonical_sha256(package)
    cache_key = canonical_sha256({
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "resolved_package_sha256": definition_digest,
        "baseline_root_sha256": base_digest,
        "tests": run_tests,
    })
    artifact = cache / "artifacts" / f"{package['name']}-{package['version']}-{cache_key}.tar.xz"
    result_path = work / package["name"] / "result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)

    if artifact.is_file():
        if realize_to is not None:
            extract_tar_xz(artifact, realize_to)
        result = {
            "schema_version": 1,
            "status": "success",
            "cache": "hit",
            "package": package["name"],
            "version": package["version"],
            "cache_key": cache_key,
            "artifact": str(artifact),
            "artifact_sha256": sha256_file(artifact),
            "baseline_root_sha256": base_digest,
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "realization_verified": True,
            "resolved_package_sha256": definition_digest,
        }
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    package_work = work / package["name"]
    clone = package_work / "root-after"
    test_clone = package_work / "root-test"
    realized = package_work / "root-realized"
    stage = package_work / "stage"
    log_path = package_work / "build.log"
    clone_root(root, clone)
    source_cwd = prepare_sources(package, clone, cache)

    command_results = []
    test_ready = False
    with log_path.open("w", encoding="utf-8") as log:
        index = 0
        for step in package["procedure"]:
            if step["condition"] == "tests-enabled" and not run_tests:
                continue
            step_cwd = resolve_working_directory(
                source_cwd, step["working_directory"]
            )
            if test_ready and step["phase"] != "test":
                source_relative = Path(source_cwd.lstrip("/"))
                test_source = test_clone / source_relative
                clone_source = clone / source_relative
                if clone_source.exists():
                    shutil.rmtree(clone_source)
                subprocess.run(
                    [
                        "cp", "-a", "--reflink=auto",
                        str(test_source), str(clone_source),
                    ],
                    check=True,
                )
                shutil.rmtree(test_clone)
                test_ready = False

            execution_root = clone
            if step["phase"] == "test":
                if not test_ready:
                    clone_root(clone, test_clone)
                    test_ready = True
                execution_root = test_clone
            for command in step["commands"]:
                index += 1
                if command.get("kind") == "session-transition":
                    item = {
                        "index": index,
                        "user": command["user"],
                        "command": command["command"],
                        "source_command": command.get("source_command"),
                        "exit_code": 0,
                        "executed": False,
                        "disposition": "recorded-session-transition",
                    }
                else:
                    with virtual_mounts(execution_root):
                        item = chroot_command(
                            execution_root, command, step_cwd, log, index
                        )
                    item["executed"] = True
                item["phase"] = step["phase"]
                command_results.append(item)
                if item["exit_code"] != 0:
                    result = {
                        "schema_version": 1,
                        "status": "failure",
                        "package": package["name"],
                        "version": package["version"],
                        "failed_command": item,
                        "commands": command_results,
                        "build_log": str(log_path),
                    }
                    result_path.write_text(
                        json.dumps(result, indent=2, sort_keys=True) + "\n"
                    )
                    return result

    if test_ready:
        shutil.rmtree(test_clone)

    after = snapshot(clone)
    changed, deleted = delta(before, after)
    if deleted:
        raise RuntimeError(
            f"{package['name']}: tar-only artifact cannot represent deletion "
            f"of baseline paths: {deleted[:20]}"
        )
    if not changed:
        raise RuntimeError(f"{package['name']}: build produced no filesystem delta")

    materialize_delta(clone, stage, changed)
    create_tar_xz(stage, artifact)

    clone_root(root, realized)
    extract_tar_xz(artifact, realized)
    realized_snapshot = snapshot(realized)
    if realized_snapshot != after:
        expected_digest = snapshot_digest(after)
        realized_digest = snapshot_digest(realized_snapshot)
        raise RuntimeError(
            f"{package['name']}: artifact realization mismatch: "
            f"{realized_digest} != {expected_digest}"
        )
    shutil.rmtree(realized)

    if realize_to is not None:
        extract_tar_xz(artifact, realize_to)

    result = {
        "schema_version": 1,
        "status": "success",
        "cache": "miss",
        "package": package["name"],
        "version": package["version"],
        "cache_key": cache_key,
        "artifact": str(artifact),
        "artifact_sha256": sha256_file(artifact),
        "baseline_root_sha256": base_digest,
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "realization_verified": True,
        "resolved_package_sha256": definition_digest,
        "changed_paths": changed,
        "commands": command_results,
        "build_log": str(log_path),
    }
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def plan(package: dict[str, Any], run_tests: bool) -> dict[str, Any]:
    commands = []
    for step in package["procedure"]:
        if step["condition"] == "tests-enabled" and not run_tests:
            continue
        for command in step["commands"]:
            commands.append({
                "phase": step["phase"],
                "working_directory": step["working_directory"],
                **command,
            })
    return {
        "schema_version": 1,
        "status": "success",
        "mode": "plan",
        "package": package["name"],
        "version": package["version"],
        "commands": commands,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="execute normalized LFS package")
    parser.add_argument("--package", required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/lfs-optimize-work"))
    parser.add_argument("--cache", type=Path, default=Path("/tmp/lfs-optimize-cache"))
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--realize-to", type=Path)
    args = parser.parse_args()

    resolved = resolve([args.package])
    package = resolved["packages"][0]
    run_tests = not args.skip_tests

    if args.plan:
        result = plan(package, run_tests)
    else:
        if args.root is None:
            parser.error("--root is required unless --plan is used")
        result = build_package(
            package, args.root, args.work, args.cache,
            run_tests, args.realize_to,
        )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
