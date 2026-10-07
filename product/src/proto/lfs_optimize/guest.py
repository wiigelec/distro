#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from blfs import resolve_blfs
from boot import PLAN_PATH, qemu_argv, require_root, require_tool
from execute import cached_download
from resolve import HERE, load_json

GUEST_MARKER_OK = "DISTRO_BLFS_EXECUTION_OK"
GUEST_MARKER_FAILED = "DISTRO_BLFS_EXECUTION_FAILED"


def guest_plan() -> dict[str, Any]:
    resolved = resolve_blfs()
    return {
        "schema_version": 1,
        "status": "success",
        "mode": "plan",
        "kind": "booted-blfs-guest-proof",
        "package_set": resolved["package_set"],
        "version_manifest": resolved["version_manifest"],
        "packages": [
            {
                "name": package["name"],
                "version": package["version"],
                "build": package.get("build", "default"),
            }
            for package in resolved["packages"]
        ],
        "execution_mode": "live-systemd-guest",
        "tests": "disabled-until-live-test-isolation-is-modeled",
        "success_marker": GUEST_MARKER_OK,
        "failure_marker": GUEST_MARKER_FAILED,
        "manual_checks_are_review_evidence": True,
        "session_transitions_execute_live": True,
    }


def run(argv: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        check=True,
        capture_output=capture,
        text=True,
    )


@contextmanager
def mounted_image(image: Path, mountpoint: Path) -> Iterator[Path]:
    mountpoint.mkdir(parents=True, exist_ok=True)
    completed = run(
        ["losetup", "--find", "--show", str(image.resolve())], capture=True
    )
    loop = completed.stdout.strip()
    if not loop:
        raise RuntimeError("losetup did not return a loop device")
    mounted = False
    try:
        run(["mount", loop, str(mountpoint.resolve())])
        mounted = True
        yield mountpoint
        run(["sync"])
    finally:
        if mounted:
            subprocess.run(["umount", str(mountpoint.resolve())], check=False)
        subprocess.run(["losetup", "-d", loop], check=False)


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(["cp", "-a", str(source), str(destination)])


def inject_prototype(root: Path) -> None:
    target = root / "opt/distro-lfs-optimize"
    target.mkdir(parents=True, exist_ok=True)
    for name in (
        "artifact.py",
        "execute.py",
        "resolve.py",
        "blfs.py",
        "live.py",
        "blfs_live.py",
        "blfs-package-set.json",
    ):
        shutil.copy2(HERE / name, target / name)
    copy_tree(HERE / "packages", target / "packages")
    copy_tree(HERE / "blfs-builds", target / "blfs-builds")
    (target / "versions").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        HERE / "versions/blfs-development.json",
        target / "versions/blfs-development.json",
    )


def prefetch_sources(host_cache: Path) -> None:
    resolved = resolve_blfs()
    for package in resolved["packages"]:
        cached_download(
            package["source"],
            host_cache,
            mirror_required=package["source"].get("mirror", "lfs") == "lfs",
        )
        for resource in package.get("resources", {}).values():
            cached_download(resource, host_cache, mirror_required=False)


def inject_sources(root: Path, host_cache: Path) -> None:
    source = host_cache / "sources"
    if not source.is_dir():
        raise RuntimeError(f"host source cache missing after prefetch: {source}")
    destination = root / "var/cache/distro-lfs-optimize/sources"
    copy_tree(source, destination)


def inject_runner(root: Path) -> None:
    target = root / "opt/distro-lfs-optimize"
    runner = target / "guest-run.sh"
    runner.write_text(
        "#!/bin/bash\n"
        "set -o pipefail\n"
        "mkdir -p /var/lib/distro-m8 /var/cache/distro-lfs-optimize\n"
        "if /usr/bin/python3 /opt/distro-lfs-optimize/blfs_live.py "
        "--work /var/lib/distro-m8/work "
        "--cache /var/cache/distro-lfs-optimize --skip-tests "
        "> /var/lib/distro-m8/runner-output.log 2>&1; then\n"
        f"  printf '{GUEST_MARKER_OK} pid1=%s kernel=%s\\n' "
        "\"$(cat /proc/1/comm)\" \"$(uname -r)\" > /dev/ttyS0\n"
        "  rc=0\n"
        "else\n"
        f"  printf '{GUEST_MARKER_FAILED} pid1=%s kernel=%s\\n' "
        "\"$(cat /proc/1/comm)\" \"$(uname -r)\" > /dev/ttyS0\n"
        "  rc=1\n"
        "fi\n"
        "sync\n"
        "/usr/bin/systemctl --no-block poweroff\n"
        "exit $rc\n",
        encoding="utf-8",
    )
    runner.chmod(0o755)

    unit_dir = root / "etc/systemd/system"
    wants = unit_dir / "multi-user.target.wants"
    wants.mkdir(parents=True, exist_ok=True)

    old_link = wants / "distro-boot-proof.service"
    old_link.unlink(missing_ok=True)
    (unit_dir / "distro-boot-proof.service").unlink(missing_ok=True)

    unit = unit_dir / "distro-blfs-proof.service"
    unit.write_text(
        "[Unit]\n"
        "Description=Booted BLFS live execution proof\n"
        "After=local-fs.target systemd-user-sessions.service\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "ExecStart=/opt/distro-lfs-optimize/guest-run.sh\n"
        "RemainAfterExit=yes\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n",
        encoding="utf-8",
    )
    link = wants / "distro-blfs-proof.service"
    link.unlink(missing_ok=True)
    link.symlink_to("/etc/systemd/system/distro-blfs-proof.service")


def collect_guest_evidence(root: Path, destination: Path) -> dict[str, Any] | None:
    source = root / "var/lib/distro-m8"
    if source.exists():
        copy_tree(source, destination)
    result = source / "result.json"
    if not result.is_file():
        return None
    return json.loads(result.read_text(encoding="utf-8"))


def run_guest(
    boot_work: Path,
    work: Path,
    cache: Path,
    timeout: int,
) -> dict[str, Any]:
    require_root()
    for tool in ("qemu-system-x86_64", "losetup", "mount", "umount", "cp"):
        require_tool(tool)

    boot_dir = boot_work.resolve() / "boot"
    boot_result_path = boot_dir / "result.json"
    if not boot_result_path.is_file():
        raise RuntimeError(f"missing successful boot evidence: {boot_result_path}")
    boot_result = json.loads(boot_result_path.read_text(encoding="utf-8"))
    if boot_result.get("status") != "success" or not boot_result.get("proof_marker_seen"):
        raise RuntimeError("boot-work does not contain a successful booted-LFS proof")

    base_image = Path(boot_result["root_image"])
    kernel = Path(boot_result["kernel"])
    if not base_image.is_file() or not kernel.is_file():
        raise RuntimeError("boot-work references missing kernel/root image")

    guest_dir = work.resolve() / "guest"
    guest_dir.mkdir(parents=True, exist_ok=True)
    image = guest_dir / "blfs-root.ext4"
    mountpoint = guest_dir / "mnt"
    console_path = guest_dir / "qemu-console.log"
    evidence_dir = guest_dir / "evidence"
    result_path = guest_dir / "result.json"

    image.unlink(missing_ok=True)
    run([
        "cp", "--reflink=auto", "--sparse=always", str(base_image), str(image)
    ])

    prefetch_sources(cache)
    with mounted_image(image, mountpoint) as root:
        inject_prototype(root)
        inject_sources(root, cache)
        inject_runner(root)

    definition = load_json(PLAN_PATH)
    argv = qemu_argv(definition, kernel, image)
    timed_out = False
    try:
        completed = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        console = completed.stdout or ""
        qemu_exit = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        raw = exc.stdout or ""
        console = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
        qemu_exit = None
    console_path.write_text(console, encoding="utf-8")

    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    guest_result = None
    with mounted_image(image, mountpoint) as root:
        guest_result = collect_guest_evidence(root, evidence_dir)

    marker_seen = GUEST_MARKER_OK in console
    payload = {
        "schema_version": 1,
        "status": "success"
        if marker_seen and guest_result and guest_result.get("status") == "success"
        else "failure",
        "kind": "booted-blfs-guest-proof",
        "boot_input_root_sha256": boot_result.get("input_root_sha256"),
        "boot_kernel_version": boot_result.get("kernel_version"),
        "base_image": str(base_image),
        "guest_image": str(image),
        "qemu_command": argv,
        "qemu_exit_code": qemu_exit,
        "qemu_timed_out": timed_out,
        "console_log": str(console_path),
        "proof_marker": GUEST_MARKER_OK,
        "proof_marker_seen": marker_seen,
        "guest_result": guest_result,
        "review_required": bool(guest_result and guest_result.get("review_required")),
        "evidence_dir": str(evidence_dir),
    }
    result_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="boot the proven LFS image and execute the M8 BLFS slice live"
    )
    parser.add_argument("--boot-work", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/lfs-optimize-m8-guest"))
    parser.add_argument("--cache", type=Path, default=Path("/tmp/lfs-optimize-cache"))
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()

    if args.plan:
        result = guest_plan()
    else:
        if args.boot_work is None:
            parser.error("--boot-work is required unless --plan is used")
        result = run_guest(args.boot_work, args.work, args.cache, args.timeout)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
