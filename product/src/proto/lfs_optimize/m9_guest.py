#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from blfs import resolve_blfs
from boot import PLAN_PATH, qemu_argv, require_root, require_tool
from execute import cached_download
from guest import copy_tree, mounted_image
from resolve import HERE, load_json

GUEST_MARKER_OK = "DISTRO_DESKTOP_PROOF_OK"
GUEST_MARKER_FAILED = "DISTRO_DESKTOP_PROOF_FAILED"
VERSIONS = HERE / "versions" / "m9-development.json"
PACKAGE_SET = HERE / "m9-package-set.json"


def guest_plan() -> dict[str, Any]:
    resolved = resolve_blfs(VERSIONS, PACKAGE_SET)
    return {
        "schema_version": 1,
        "status": "success",
        "mode": "plan",
        "kind": "booted-m9-functional-system-proof",
        "base_requirement": "successful review-clean M8 PAM login proof image",
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
        "interactive_desktop": {
            "mode": "--interactive",
            "server": "Xorg",
            "display": ":0",
            "gpu": "virtio-vga",
            "pointer": "usb-tablet",
            "host_display": "gtk,grab-on-hover=off",
            "systemd_target": "graphical.target",
            "source_image": "successful M9 guest image",
            "automated_xvfb_proof_unchanged": True,
        },
        "runtime_acceptance": {
            "network": {
                "manager": "NetworkManager",
                "competing_manager_inactive": "systemd-networkd",
                "interface": "QEMU virtio Ethernet",
                "requires_managed_connected_state": True,
                "requires_ipv4_address": True,
                "public_internet_required": False,
            },
            "desktop": {
                "server": "Xvfb",
                "display": ":99",
                "session": "icewm-session",
                "process": "icewm",
                "requires_matching_display_environment": True,
                "font": "DejaVu via Fontconfig",
            },
        },
        "success_marker": GUEST_MARKER_OK,
        "failure_marker": GUEST_MARKER_FAILED,
        "cache_policy": {
            "host_guest_roundtrip": ["sources", "artifacts", "evidence"],
            "salvage_existing_guest_before_replace": True,
        },
        "superseded_proof_units": [
            "distro-boot-proof.service",
            "distro-blfs-proof.service",
            "distro-pam-login-proof.service",
        ],
    }


def run(argv: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, capture_output=capture, text=True)


def inject_prototype(root: Path) -> None:
    target = root / "opt/distro-lfs-optimize"
    target.mkdir(parents=True, exist_ok=True)
    for name in (
        "artifact.py",
        "execute.py",
        "resolve.py",
        "blfs.py",
        "live.py",
        "m9_live.py",
        "m9-package-set.json",
    ):
        shutil.copy2(HERE / name, target / name)
    copy_tree(HERE / "packages", target / "packages")
    copy_tree(HERE / "blfs-builds", target / "blfs-builds")
    copy_tree(HERE / "collections", target / "collections")
    (target / "versions").mkdir(parents=True, exist_ok=True)
    shutil.copy2(VERSIONS, target / "versions/m9-development.json")


def prefetch_sources(host_cache: Path) -> None:
    resolved = resolve_blfs(VERSIONS, PACKAGE_SET)
    for package in resolved["packages"]:
        cached_download(
            package["source"],
            host_cache,
            mirror_required=package["source"].get("mirror", "lfs") == "lfs",
        )
        for resource in package.get("resources", {}).values():
            cached_download(resource, host_cache, mirror_required=False)


def merge_cache_directory(source: Path, destination: Path) -> None:
    if not source.is_dir():
        return
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)


def inject_cache(root: Path, host_cache: Path) -> None:
    sources = host_cache / "sources"
    if not sources.is_dir():
        raise RuntimeError(f"host source cache missing after prefetch: {sources}")
    guest_cache = root / "var/cache/distro-lfs-optimize"
    for name in ("sources", "artifacts", "evidence"):
        merge_cache_directory(host_cache / name, guest_cache / name)


def harvest_cache(root: Path, host_cache: Path) -> None:
    guest_cache = root / "var/cache/distro-lfs-optimize"
    for name in ("artifacts", "evidence"):
        merge_cache_directory(guest_cache / name, host_cache / name)


def inject_runner(root: Path) -> None:
    target = root / "opt/distro-lfs-optimize"
    runner = target / "m9-guest-run.sh"
    runner.write_text(
        "#!/bin/bash\n"
        "set -o pipefail\n"
        "mkdir -p /var/lib/distro-m8/m9-runtime /var/cache/distro-lfs-optimize\n"
        "if /usr/bin/python3 /opt/distro-lfs-optimize/m9_live.py "
        "--work /var/lib/distro-m8/m9-runtime/work "
        "--cache /var/cache/distro-lfs-optimize "
        "--result /var/lib/distro-m8/m9-runtime/result.json "
        "--skip-tests "
        "> /var/lib/distro-m8/m9-runtime/runner-output.log 2>&1; then\n"
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

    for old in (
        "distro-boot-proof.service",
        "distro-blfs-proof.service",
        "distro-pam-login-proof.service",
    ):
        (wants / old).unlink(missing_ok=True)
        (unit_dir / old).unlink(missing_ok=True)

    unit = unit_dir / "distro-m9-proof.service"
    unit.write_text(
        "[Unit]\n"
        "Description=Booted M9 NetworkManager + IceWM proof\n"
        "After=local-fs.target dbus.service systemd-user-sessions.service\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "ExecStart=/opt/distro-lfs-optimize/m9-guest-run.sh\n"
        "RemainAfterExit=yes\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n",
        encoding="utf-8",
    )
    link = wants / "distro-m9-proof.service"
    link.unlink(missing_ok=True)
    link.symlink_to("/etc/systemd/system/distro-m9-proof.service")


def inject_interactive_desktop(root: Path) -> None:
    unit_dir = root / "etc/systemd/system"
    (unit_dir / "multi-user.target.wants/distro-m9-proof.service").unlink(missing_ok=True)

    target = root / "opt/distro-lfs-optimize"
    target.mkdir(parents=True, exist_ok=True)
    runner = target / "m9-desktop-start.sh"
    runner.write_text(
        "#!/bin/bash\n"
        "set -eu\n"
        "systemctl mask --runtime systemd-networkd.service systemd-networkd.socket || true\n"
        "systemctl stop systemd-networkd.socket systemd-networkd.service "
        "systemd-networkd-persistent-storage.service || true\n"
        "systemctl restart NetworkManager.service || true\n"
        "install -d -m700 /run/user/0\n"
        "rm -f /tmp/.X0-lock /tmp/.X11-unix/X0\n"
        "/usr/bin/Xorg :0 -nolisten tcp > /var/log/m9-xorg.log 2>&1 &\n"
        "xpid=$!\n"
        "for _ in $(seq 1 100); do\n"
        "  test -S /tmp/.X11-unix/X0 && break\n"
        "  kill -0 \"$xpid\" 2>/dev/null || exit 1\n"
        "  sleep 0.1\n"
        "done\n"
        "test -S /tmp/.X11-unix/X0\n"
        "export DISPLAY=:0 HOME=/root XDG_RUNTIME_DIR=/run/user/0\n"
        "exec /usr/bin/icewm-session\n",
        encoding="utf-8",
    )
    runner.chmod(0o755)

    unit = unit_dir / "distro-m9-desktop.service"
    unit.write_text(
        "[Unit]\n"
        "Description=Interactive M9 Xorg + IceWM desktop\n"
        "After=local-fs.target dbus.service systemd-user-sessions.service\n\n"
        "[Service]\n"
        "Type=simple\n"
        "ExecStart=/opt/distro-lfs-optimize/m9-desktop-start.sh\n"
        "Restart=on-failure\n"
        "RestartSec=2\n\n"
        "[Install]\n"
        "WantedBy=graphical.target\n",
        encoding="utf-8",
    )
    wants = unit_dir / "graphical.target.wants"
    wants.mkdir(parents=True, exist_ok=True)
    link = wants / "distro-m9-desktop.service"
    link.unlink(missing_ok=True)
    link.symlink_to("/etc/systemd/system/distro-m9-desktop.service")


def interactive_qemu_argv(definition: dict[str, Any], kernel: Path, image: Path) -> list[str]:
    argv = qemu_argv(definition, kernel, image)
    argv.remove("-nographic")
    append_index = argv.index("-append") + 1
    argv[append_index] = argv[append_index].replace(
        "systemd.unit=multi-user.target",
        "systemd.unit=graphical.target",
    )
    argv.extend([
        "-vga", "none",
        "-device", "virtio-vga",
        "-device", "usb-tablet",
        "-display", "gtk,grab-on-hover=off",
        "-serial", "mon:stdio",
    ])
    return argv


def run_interactive(boot_work: Path, work: Path) -> dict[str, Any]:
    require_root()
    for tool in ("qemu-system-x86_64", "losetup", "mount", "umount", "cp"):
        require_tool(tool)

    boot_result_path = boot_work.resolve() / "boot/result.json"
    if not boot_result_path.is_file():
        raise RuntimeError(f"missing boot result: {boot_result_path}")
    boot_result = json.loads(boot_result_path.read_text(encoding="utf-8"))
    kernel = Path(boot_result["kernel"])
    if not kernel.is_file():
        raise RuntimeError(f"boot result references missing kernel: {kernel}")

    guest_dir = work.resolve() / "m9-guest"
    source_image = guest_dir / "m9-root.ext4"
    if not source_image.is_file():
        raise RuntimeError(
            f"interactive mode requires an existing successful M9 image: {source_image}"
        )

    image = guest_dir / "m9-desktop.ext4"
    mountpoint = guest_dir / "desktop-mnt"
    image.unlink(missing_ok=True)
    run(["cp", "--reflink=auto", "--sparse=always", str(source_image), str(image)])
    with mounted_image(image, mountpoint) as root:
        inject_interactive_desktop(root)

    definition = load_json(PLAN_PATH)
    argv = interactive_qemu_argv(definition, kernel, image)
    completed = subprocess.run(argv, check=False)
    return {
        "schema_version": 1,
        "status": "success" if completed.returncode == 0 else "failure",
        "kind": "interactive-m9-icewm-vm",
        "guest_image": str(image),
        "kernel": str(kernel),
        "qemu_command": argv,
        "qemu_exit_code": completed.returncode,
        "display": ":0",
        "gpu": "virtio-vga",
    }


def run_guest(boot_work: Path, m8_auth_work: Path, work: Path, cache: Path, timeout: int) -> dict[str, Any]:
    require_root()
    for tool in ("qemu-system-x86_64", "losetup", "mount", "umount", "cp"):
        require_tool(tool)

    boot_result_path = boot_work.resolve() / "boot/result.json"
    if not boot_result_path.is_file():
        raise RuntimeError(f"missing boot result: {boot_result_path}")
    boot_result = json.loads(boot_result_path.read_text(encoding="utf-8"))
    if boot_result.get("status") != "success" or not boot_result.get("proof_marker_seen"):
        raise RuntimeError("boot-work does not contain a successful booted-LFS proof")

    m8_auth_result_path = m8_auth_work.resolve() / "auth/result.json"
    if not m8_auth_result_path.is_file():
        raise RuntimeError(f"missing M8 PAM acceptance result: {m8_auth_result_path}")
    m8_auth_result = json.loads(m8_auth_result_path.read_text(encoding="utf-8"))
    if (
        m8_auth_result.get("status") != "success"
        or not m8_auth_result.get("proof_marker_seen")
        or not m8_auth_result.get("pam_login_verified")
        or m8_auth_result.get("review_required")
    ):
        raise RuntimeError(
            "m8-auth-work does not contain a successful review-clean M8 PAM login proof"
        )

    base_image = Path(m8_auth_result["auth_image"])
    kernel = Path(boot_result["kernel"])
    if not base_image.is_file() or not kernel.is_file():
        raise RuntimeError("M8/boot evidence references a missing guest image or kernel")

    guest_dir = work.resolve() / "m9-guest"
    guest_dir.mkdir(parents=True, exist_ok=True)
    image = guest_dir / "m9-root.ext4"
    mountpoint = guest_dir / "mnt"
    console_path = guest_dir / "qemu-console.log"
    evidence_dir = guest_dir / "evidence"
    result_path = guest_dir / "result.json"

    if image.is_file():
        with mounted_image(image, mountpoint) as previous_root:
            harvest_cache(previous_root, cache)

    image.unlink(missing_ok=True)
    run(["cp", "--reflink=auto", "--sparse=always", str(base_image), str(image)])

    prefetch_sources(cache)
    with mounted_image(image, mountpoint) as root:
        inject_prototype(root)
        inject_cache(root, cache)
        inject_runner(root)

    definition = load_json(PLAN_PATH)
    argv = qemu_argv(definition, kernel, image)
    timed_out = False
    console_parts: list[str] = []
    with console_path.open("w", encoding="utf-8") as console_file:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        def pump_console() -> None:
            if process.stdout is None:
                return
            for line in process.stdout:
                console_parts.append(line)
                console_file.write(line)
                console_file.flush()
                sys.stdout.write(line)
                sys.stdout.flush()

        reader = threading.Thread(target=pump_console, daemon=True)
        reader.start()
        try:
            qemu_exit = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            qemu_exit = None
        reader.join(timeout=5)
    console = "".join(console_parts)

    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    guest_result = None
    with mounted_image(image, mountpoint) as root:
        harvest_cache(root, cache)
        source = root / "var/lib/distro-m8/m9-runtime"
        if source.exists():
            copy_tree(source, evidence_dir)
        result = source / "result.json"
        if result.is_file():
            guest_result = json.loads(result.read_text(encoding="utf-8"))

    marker_seen = GUEST_MARKER_OK in console
    payload = {
        "schema_version": 1,
        "status": "success"
        if marker_seen
        and guest_result
        and guest_result.get("status") == "success"
        and guest_result.get("networkmanager_verified")
        and guest_result.get("icewm_verified")
        and not guest_result.get("review_required")
        else "failure",
        "kind": "booted-m9-functional-system-proof",
        "m8_auth_input_result": str(m8_auth_result_path),
        "base_image": str(base_image),
        "guest_image": str(image),
        "kernel": str(kernel),
        "qemu_command": argv,
        "qemu_exit_code": qemu_exit,
        "qemu_timed_out": timed_out,
        "console_log": str(console_path),
        "proof_marker": GUEST_MARKER_OK,
        "proof_marker_seen": marker_seen,
        "guest_result": guest_result,
        "networkmanager_verified": bool(guest_result and guest_result.get("networkmanager_verified")),
        "icewm_verified": bool(guest_result and guest_result.get("icewm_verified")),
        "review_required": bool(guest_result and guest_result.get("review_required")),
        "evidence_dir": str(evidence_dir),
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="boot the review-clean M8 PAM acceptance image and execute the M9 functional-system proof"
    )
    parser.add_argument("--boot-work", type=Path)
    parser.add_argument("--m8-auth-work", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/lfs-optimize-m9-guest"))
    parser.add_argument("--cache", type=Path, default=Path("/tmp/lfs-optimize-cache"))
    parser.add_argument("--timeout", type=int, default=10800)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()

    if args.plan:
        result = guest_plan()
    elif args.interactive:
        if args.boot_work is None:
            parser.error("--boot-work is required with --interactive")
        result = run_interactive(args.boot_work, args.work)
    else:
        if args.boot_work is None or args.m8_auth_work is None:
            parser.error("--boot-work and --m8-auth-work are required unless --plan or --interactive is used")
        result = run_guest(args.boot_work, args.m8_auth_work, args.work, args.cache, args.timeout)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
