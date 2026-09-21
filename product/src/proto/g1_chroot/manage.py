#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path

DEFAULT_REPOSITORY = Path.home() / "distro-g1-chroot" / "repository"
DEFAULT_ROOT = Path.home() / "distro-g1-root"
STATE_PATH = Path("var/lib/distro/manage/installed.json")
ROOT_DIRECTORIES = {
    Path("tmp"): 0o1777,
    Path("var/tmp"): 0o1777,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_database(repository: Path) -> dict[str, dict]:
    database_path = repository / "database.json"
    database = json.loads(database_path.read_text(encoding="utf-8"))
    if database.get("schema_version") != 1:
        raise RuntimeError("unsupported repository database schema")

    result = {}
    for record in database.get("packages", []):
        name = record["identity"]["name"]
        if name in result:
            raise RuntimeError(f"duplicate repository package: {name}")
        result[name] = record
    return result


def resolve(packages: dict[str, dict], requested: str) -> list[str]:
    order = []
    visiting = set()
    visited = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise RuntimeError(f"dependency cycle involving {name}")
        record = packages.get(name)
        if record is None:
            raise RuntimeError(f"repository package not found: {name}")

        visiting.add(name)
        for dependency in record.get("depends", []):
            if set(dependency) != {"name"}:
                raise RuntimeError(
                    f"{name}: prototype supports only unconstrained named dependencies"
                )
            visit(dependency["name"])
        visiting.remove(name)
        visited.add(name)
        order.append(name)

    visit(requested)
    return order


def validate_member(member: tarfile.TarInfo) -> None:
    path = Path(member.name)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"unsafe package path: {member.name}")
    if member.islnk():
        link = Path(member.linkname)
        if link.is_absolute() or ".." in link.parts:
            raise RuntimeError(f"unsafe hard-link target: {member.name}")
        if not link.parts or link.parts[0] != "root":
            raise RuntimeError(
                f"hard-link target must remain inside root payload: {member.name}"
            )
    if member.issym():
        link = Path(member.linkname)
        if link.is_absolute():
            raise RuntimeError(f"absolute symlink is not supported: {member.name}")
        destination = Path("/") / path.parent / link
        normalized = Path(os.path.normpath(str(destination)))
        if ".." in normalized.parts:
            raise RuntimeError(f"unsafe symlink target: {member.name}")


def inspect_artifact(repository: Path, record: dict) -> tuple[Path, dict]:
    artifact = repository / record["artifact"]
    if sha256_file(artifact) != record["artifact_sha256"]:
        raise RuntimeError(f"artifact checksum mismatch: {artifact.name}")

    with tarfile.open(artifact, "r:*") as tar:
        for member in tar.getmembers():
            validate_member(member)
        metadata_member = tar.getmember("metadata.json")
        handle = tar.extractfile(metadata_member)
        if handle is None:
            raise RuntimeError(f"{artifact.name}: missing metadata")
        metadata = json.loads(handle.read().decode("utf-8"))

    if metadata["identity"] != record["identity"]:
        raise RuntimeError(f"{artifact.name}: embedded identity mismatch")
    if metadata.get("owned_paths", []) != record.get("owned_paths", []):
        raise RuntimeError(f"{artifact.name}: owned-path metadata mismatch")
    return artifact, metadata


def load_state(root: Path) -> dict:
    path = root / STATE_PATH
    if not path.is_file():
        return {"schema_version": 1, "packages": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1:
        raise RuntimeError("unsupported installed-state schema")
    return state


def preflight(root: Path, packages: dict[str, dict], order: list[str], state: dict) -> None:
    installed_owners = {}
    for name, record in state.get("packages", {}).items():
        for owned in record.get("owned_paths", []):
            installed_owners[owned] = name

    pending_owners = {}
    for name in order:
        for owned in packages[name].get("owned_paths", []):
            previous = pending_owners.get(owned)
            if previous is not None and previous != name:
                raise RuntimeError(
                    f"package path conflict: {owned}: {previous} and {name}"
                )
            installed = installed_owners.get(owned)
            if installed is not None and installed != name:
                raise RuntimeError(
                    f"installed path conflict: {owned}: {installed} and {name}"
                )
            target = root / owned
            if target.exists() or target.is_symlink():
                if installed != name:
                    raise RuntimeError(f"unowned target path already exists: {owned}")
            pending_owners[owned] = name


def install_artifact(root: Path, artifact: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="distro-manage-") as temporary:
        temp = Path(temporary)
        with tarfile.open(artifact, "r:*") as tar:
            for member in tar.getmembers():
                validate_member(member)
            tar.extractall(temp, filter="data")

        payload = temp / "root"
        if not payload.is_dir():
            raise RuntimeError(f"{artifact.name}: missing root payload")

        hardlinks = {}
        for source in sorted(payload.rglob("*")):
            relative = source.relative_to(payload)
            target = root / relative

            if source.is_dir() and not source.is_symlink():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()

            if source.is_symlink():
                target.symlink_to(os.readlink(source))
                continue

            stat = source.stat(follow_symlinks=False)
            inode_key = (stat.st_dev, stat.st_ino)
            existing = hardlinks.get(inode_key)
            if stat.st_nlink > 1 and existing is not None:
                os.link(existing, target)
            else:
                shutil.copy2(source, target, follow_symlinks=False)
                if stat.st_nlink > 1:
                    hardlinks[inode_key] = target


def prepare_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for relative, mode in ROOT_DIRECTORIES.items():
        directory = root / relative
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(mode)


def finalize_root(root: Path) -> None:
    usr_bin = root / "usr/bin"
    bash = usr_bin / "bash"
    sh = usr_bin / "sh"
    if bash.exists() and not sh.exists() and not sh.is_symlink():
        sh.symlink_to("bash")

    bin_path = root / "bin"
    if not bin_path.exists() and not bin_path.is_symlink():
        bin_path.symlink_to("usr/bin")


def install(repository: Path, root: Path, requested: str) -> dict:
    prepare_root(root)
    packages = load_database(repository)
    order = resolve(packages, requested)
    state = load_state(root)

    artifacts = {}
    for name in order:
        artifact, _metadata = inspect_artifact(repository, packages[name])
        artifacts[name] = artifact

    preflight(root, packages, order, state)

    installed = state.setdefault("packages", {})
    for name in order:
        install_artifact(root, artifacts[name])
        installed[name] = {
            "identity": packages[name]["identity"],
            "owned_paths": packages[name].get("owned_paths", []),
            "install_reason": "explicit" if name == requested else "dependency",
        }

    finalize_root(root)

    state_path = root / STATE_PATH
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return {
        "status": "installed",
        "requested": requested,
        "repository": str(repository),
        "root": str(root),
        "install_order": order,
        "state": str(state_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="G1 chroot Manage prototype")
    parser.add_argument(
        "--repository",
        type=Path,
        default=DEFAULT_REPOSITORY,
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("package")

    args = parser.parse_args()
    if args.command == "install":
        print(json.dumps(
            install(args.repository, args.root, args.package),
            indent=2,
            sort_keys=True,
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
