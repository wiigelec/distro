#!/usr/bin/env python3
"""Drive the package-closed build and installer ISO pipeline."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


INSTALLED_DB = Path("var/lib/distro/manage/installed.json")
ALLOWED_GENERATED = {INSTALLED_DB.as_posix()}


def repository_root():
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "product/src/proto/manager/manage.py").is_file():
            return parent
    raise RuntimeError("unable to locate distro repository root")


def require_root():
    if os.geteuid() != 0:
        raise RuntimeError("closed pipeline must run as root")


def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def manage_install(repository, root, package):
    manager = repository_root() / "product/src/proto/manager/manage.py"
    run([
        shutil.which("python3") or "/usr/bin/python3",
        str(manager),
        "install",
        "--repository", str(repository),
        "--root", str(root),
        package,
    ])


def audit_managed_root(root):
    database = json.loads((root / INSTALLED_DB).read_text())
    owned = set()
    for record in database["packages"]:
        owned.update(record.get("owned_paths", []))

    unowned = []
    for path in sorted(root.rglob("*")):
        if not (path.is_file() or path.is_symlink()):
            continue
        relative = path.relative_to(root).as_posix()
        if relative in ALLOWED_GENERATED:
            continue
        if relative not in owned:
            unowned.append(relative)

    if unowned:
        raise RuntimeError(
            "managed-root closure failure; unowned files: "
            + ", ".join(unowned[:50])
        )

    return {
        "status": "success",
        "owned_file_count": len(owned),
        "unowned_paths": [],
        "allowed_generated_paths": sorted(ALLOWED_GENERATED),
    }


def mount_bind(source, target, readonly=False, recursive=False):
    target.mkdir(parents=True, exist_ok=True)
    flag = "--rbind" if recursive else "--bind"
    run(["mount", flag, str(source), str(target)])

    if recursive:
        # Prevent mount events in the chroot from propagating back into the
        # host tree and make nested /dev/pts teardown deterministic.
        run(["mount", "--make-rslave", str(target)])

    if readonly:
        run(["mount", "-o", "remount,bind,ro", str(target)])


def unmount(target):
    result = subprocess.run(
        ["umount", "-R", str(target)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        subprocess.run(
            ["umount", "-R", "-l", str(target)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def run_in_build_root(root, args, binds):
    mounted = []
    try:
        for source, destination, readonly, recursive in binds:
            target = root / destination.lstrip("/")
            mount_bind(source, target, readonly=readonly, recursive=recursive)
            mounted.append(target)

        for pseudo in ("proc", "sys", "dev"):
            source = Path("/") / pseudo
            target = root / pseudo
            mount_bind(source, target, readonly=False, recursive=(pseudo == "dev"))
            mounted.append(target)

        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        resolver = root / "etc/resolv.conf"
        if not resolver.is_file():
            raise RuntimeError(
                "closed build root has no package-owned /etc/resolv.conf"
            )

        run(
            ["chroot", str(root), *args],
            env=env,
        )
    finally:
        for target in reversed(mounted):
            unmount(target)


def pipeline(seed_repository, output, iso):
    require_root()

    seed_repository = seed_repository.resolve()
    if not (seed_repository / "database.json").is_file():
        raise RuntimeError(f"invalid seed repository: {seed_repository}")

    output = output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    build_root = output / "build-root"
    build_root.mkdir()
    manage_install(seed_repository, build_root, "build-system")
    build_audit_before = audit_managed_root(build_root)

    generated = output / "generated"
    generated.mkdir()

    run_in_build_root(
        build_root,
        [
            "/usr/bin/python3",
            "/opt/distro/proto/bootstrap/inside_build.py",
            "build-repositories",
            "--seed-repository", "/work/seed",
            "--output", "/work/generated",
        ],
        [
            (seed_repository, "/work/seed", True, False),
            (generated, "/work/generated", False, False),
        ],
    )

    build_audit_after = audit_managed_root(build_root)

    installer_repository = generated / "installer-repository"
    installer_root = output / "installer-root"
    installer_root.mkdir()
    manage_install(installer_repository, installer_root, "installer-runtime")
    installer_audit = audit_managed_root(installer_root)

    iso_output = iso.resolve()
    iso_output.parent.mkdir(parents=True, exist_ok=True)

    run_in_build_root(
        build_root,
        [
            "/usr/bin/python3",
            "/opt/distro/proto/bootstrap/inside_build.py",
            "assemble-iso",
            "--iso-root", "/work/installer-root",
            "--output", "/work/final.iso",
        ],
        [
            (iso_output.parent, "/work", False, False),
            (installer_root, "/work/installer-root", True, False),
        ],
    )

    # inside_build writes /work/final.iso; normalize to the requested path.
    produced = iso_output.parent / "final.iso"
    if produced != iso_output:
        if iso_output.exists():
            iso_output.unlink()
        produced.replace(iso_output)

    result = {
        "schema_version": 1,
        "status": "success",
        "seed_repository": str(seed_repository),
        "system_repository": str(generated / "system-repository"),
        "installer_repository": str(installer_repository),
        "build_root": {
            "path": str(build_root),
            "audit_before": build_audit_before,
            "audit_after": build_audit_after,
        },
        "installer_root": {
            "path": str(installer_root),
            "audit": installer_audit,
        },
        "iso": str(iso_output),
        "closure": {
            "host_package_content_after_stage0": [],
            "build_root_source": "Manage install build-system",
            "installer_root_source": "Manage install installer-runtime",
            "iso_tools_source": "package:bootstrap-tools",
            "bootloader_source": "package:bootstrap-tools",
            "kernel_source": "package:bootstrap-tools",
        },
    }
    (output / "closure-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run the Distro package-closed prototype pipeline"
    )
    parser.add_argument(
        "--seed-repository",
        type=Path,
        default=Path("/tmp/distro-seed-repo"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/distro-closed"),
    )
    parser.add_argument(
        "--iso",
        type=Path,
        default=Path("/tmp/distro-closed-installer.iso"),
    )
    args = parser.parse_args()

    print(json.dumps(
        pipeline(args.seed_repository, args.output, args.iso),
        indent=2,
        sort_keys=True,
    ))


if __name__ == "__main__":
    main()
