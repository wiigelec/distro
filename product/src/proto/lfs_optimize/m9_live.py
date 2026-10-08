#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from artifact import snapshot_digest
from blfs import resolve_blfs
from live import build_package_live, live_snapshot
from resolve import HERE

VERSIONS = HERE / "versions" / "m9-development.json"
PACKAGE_SET = HERE / "m9-package-set.json"


def serial_progress(message: str) -> None:
    line = f"[M9] {message}\n"
    try:
        with Path("/dev/ttyS0").open("a", encoding="utf-8") as serial:
            serial.write(line)
            serial.flush()
    except OSError:
        print(line, end="", flush=True)


def capture(argv: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=check, capture_output=True, text=True, env=env)


def systemd_version() -> str:
    return capture(["systemctl", "--version"]).stdout.splitlines()[0]


def cleanup_source(package: dict[str, Any]) -> None:
    path = Path("/tmp/distro-lfs-optimize") / f"{package['name']}-{package['version']}"
    shutil.rmtree(path, ignore_errors=True)


def network_acceptance() -> dict[str, Any]:
    networkd_service = "systemd-networkd.service"
    networkd_socket = "systemd-networkd.socket"
    persistent_storage = "systemd-networkd-persistent-storage.service"

    capture([
        "systemctl",
        "mask",
        "--runtime",
        networkd_service,
        networkd_socket,
    ])
    capture(["systemctl", "daemon-reload"])
    capture(
        ["systemctl", "stop", networkd_socket, networkd_service, persistent_storage],
        check=False,
    )

    terminal_states = {"inactive", "failed", "not-found"}

    def networkd_state(unit: str) -> str:
        state = capture(
            ["systemctl", "show", "--property=ActiveState", "--value", unit],
            check=False,
        ).stdout.strip()
        return state or "not-found"

    deadline = time.monotonic() + 10.0
    while True:
        networkd_before = networkd_state(networkd_service)
        networkd_socket_before = networkd_state(networkd_socket)
        if (
            networkd_before in terminal_states
            and networkd_socket_before in terminal_states
        ):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "systemd-networkd did not quiesce before NetworkManager handoff: "
                f"service={networkd_before!r} socket={networkd_socket_before!r}"
            )
        time.sleep(0.1)

    capture(["systemctl", "enable", "NetworkManager.service"])
    capture(["systemctl", "restart", "NetworkManager.service"])

    status = capture(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"]).stdout
    interface = None
    for line in status.splitlines():
        fields = line.split(":")
        if len(fields) >= 2 and fields[1] == "ethernet":
            interface = fields[0]
            break
    if not interface:
        raise RuntimeError(f"NetworkManager did not expose an Ethernet device: {status!r}")

    capture(["nmcli", "device", "set", interface, "managed", "yes"])
    subprocess.run(["nmcli", "connection", "delete", "distro-m9"], check=False, capture_output=True, text=True)
    capture([
        "nmcli", "connection", "add",
        "type", "ethernet",
        "ifname", interface,
        "con-name", "distro-m9",
        "ipv4.method", "auto",
        "ipv6.method", "disabled",
    ])
    capture(["nmcli", "connection", "up", "distro-m9"])
    capture(["nm-online", "--quiet", "--timeout=30"])

    service_state = capture(["systemctl", "is-active", "NetworkManager.service"]).stdout.strip()
    device_state = capture(["nmcli", "-g", "GENERAL.STATE", "device", "show", interface]).stdout.strip()
    address = capture(["nmcli", "-g", "IP4.ADDRESS", "device", "show", interface]).stdout.strip().splitlines()
    networkd = networkd_state(networkd_service)
    networkd_socket_state = networkd_state(networkd_socket)

    if service_state != "active":
        raise RuntimeError(f"NetworkManager is not active: {service_state}")
    if not device_state.startswith("100"):
        raise RuntimeError(f"{interface} is not connected under NetworkManager: {device_state}")
    if not address or not address[0]:
        raise RuntimeError(f"{interface} did not acquire an IPv4 address")
    if networkd not in terminal_states or networkd_socket_state not in terminal_states:
        raise RuntimeError(
            "systemd-networkd became active during NetworkManager acceptance: "
            f"service={networkd!r} socket={networkd_socket_state!r}"
        )

    return {
        "manager": "NetworkManager",
        "service_active": True,
        "interface": interface,
        "device_state": device_state,
        "ipv4_address": address[0],
        "systemd_networkd_active": False,
        "systemd_networkd_socket_active": False,
        "connectivity_scope": "QEMU user-mode network DHCP; no public-Internet dependency",
    }


def wait_for(predicate, description: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for {description}")


def desktop_acceptance(evidence_dir: Path) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    xvfb_log = evidence_dir / "xvfb.log"
    icewm_log = evidence_dir / "icewm-session.log"
    xdg_runtime = Path("/tmp/distro-m9-xdg")
    xdg_runtime.mkdir(mode=0o700, exist_ok=True)

    xvfb_handle = xvfb_log.open("w", encoding="utf-8")
    icewm_handle = icewm_log.open("w", encoding="utf-8")
    xvfb = None
    session = None
    try:
        xvfb = subprocess.Popen(
            ["Xvfb", ":99", "-screen", "0", "1024x768x24", "-nolisten", "tcp"],
            stdout=xvfb_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        socket = Path("/tmp/.X11-unix/X99")
        wait_for(
            lambda: xvfb.poll() is None and socket.exists(),
            "Xvfb display :99",
        )

        font_match = capture(["fc-match", "sans-serif"]).stdout.strip()
        if "DejaVu" not in font_match:
            raise RuntimeError(f"Fontconfig did not select DejaVu for sans-serif: {font_match}")

        env = os.environ.copy()
        env.update({
            "DISPLAY": ":99",
            "HOME": "/root",
            "XDG_RUNTIME_DIR": str(xdg_runtime),
        })
        session = subprocess.Popen(
            ["icewm-session"],
            stdout=icewm_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        def icewm_pid() -> int | None:
            completed = subprocess.run(
                ["pgrep", "-x", "icewm"],
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                return None
            for line in completed.stdout.splitlines():
                if line.strip().isdigit():
                    return int(line.strip())
            return None

        wait_for(lambda: session.poll() is None and icewm_pid() is not None, "IceWM process")
        pid = icewm_pid()
        if pid is None:
            raise RuntimeError("IceWM process disappeared after startup")
        environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        if b"DISPLAY=:99" not in environ:
            raise RuntimeError("IceWM process is not bound to Xvfb display :99")
        if xvfb.poll() is not None:
            raise RuntimeError("Xvfb exited during IceWM acceptance")

        return {
            "display": ":99",
            "xvfb_running": True,
            "x_socket": str(socket),
            "icewm_session_running": True,
            "icewm_pid": pid,
            "icewm_display_verified": True,
            "font_match": font_match,
            "xvfb_log": str(xvfb_log),
            "icewm_log": str(icewm_log),
        }
    finally:
        if session is not None and session.poll() is None:
            session.terminate()
            try:
                session.wait(timeout=5)
            except subprocess.TimeoutExpired:
                session.kill()
        subprocess.run(["pkill", "-x", "icewm"], check=False)
        if xvfb is not None and xvfb.poll() is None:
            xvfb.terminate()
            try:
                xvfb.wait(timeout=5)
            except subprocess.TimeoutExpired:
                xvfb.kill()
        xvfb_handle.close()
        icewm_handle.close()
        shutil.rmtree(xdg_runtime, ignore_errors=True)


def run_m9(work: Path, cache: Path, result_path: Path, run_tests: bool) -> dict[str, Any]:
    if Path("/proc/1/comm").read_text(encoding="utf-8").strip() != "systemd":
        raise RuntimeError("M9 live proof requires systemd as PID 1")
    if run_tests:
        raise RuntimeError("M9 live proof currently requires --skip-tests")

    resolved = resolve_blfs(VERSIONS, PACKAGE_SET)
    work.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    serial_progress("initial snapshot")
    initial_snapshot = live_snapshot(Path("/"))
    initial_digest = snapshot_digest(initial_snapshot)
    serial_progress("initial snapshot complete")
    package_results: list[dict[str, Any]] = []
    current_root_digest = initial_digest
    current_snapshot: dict[str, dict[str, Any]] | None = initial_snapshot

    for package in resolved["packages"]:
        result = build_package_live(
            package,
            Path("/"),
            work / "packages",
            cache,
            run_tests=False,
            progress=serial_progress,
            baseline_root_sha256=current_root_digest,
            baseline_snapshot=current_snapshot,
        )
        package_results.append(result)
        cleanup_source(package)
        if result["status"] == "success":
            current_root_digest = result["final_root_sha256"]
            current_snapshot = None
        if result["status"] != "success":
            payload = {
                "schema_version": 1,
                "status": "failure",
                "kind": "booted-m9-functional-system-proof",
                "package_set": resolved["package_set"],
                "version_manifest": resolved["version_manifest"],
                "kernel": platform.release(),
                "pid1": "systemd",
                "systemd": systemd_version(),
                "initial_root_sha256": initial_digest,
                "failed_package": package["name"],
                "packages": package_results,
                "review_required": any(item.get("review_required") for item in package_results),
            }
            result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            serial_progress(f"{package['name']} failed")
            return payload

    build_digest = current_root_digest
    serial_progress("build cache chain complete")
    evidence_dir = result_path.parent / "runtime"
    try:
        serial_progress("runtime network acceptance")
        network = network_acceptance()
        serial_progress("runtime network acceptance complete")
        serial_progress("runtime desktop acceptance")
        desktop = desktop_acceptance(evidence_dir)
        serial_progress("runtime desktop acceptance complete")
        payload = {
            "schema_version": 1,
            "status": "success",
            "kind": "booted-m9-functional-system-proof",
            "package_set": resolved["package_set"],
            "version_manifest": resolved["version_manifest"],
            "kernel": platform.release(),
            "pid1": "systemd",
            "systemd": systemd_version(),
            "initial_root_sha256": initial_digest,
            "built_root_sha256": build_digest,
            "packages": package_results,
            "network": network,
            "desktop": desktop,
            "networkmanager_verified": True,
            "icewm_verified": True,
            "review_required": any(item.get("review_required") for item in package_results),
        }
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "status": "failure",
            "kind": "booted-m9-functional-system-proof",
            "package_set": resolved["package_set"],
            "version_manifest": resolved["version_manifest"],
            "kernel": platform.release(),
            "pid1": "systemd",
            "systemd": systemd_version(),
            "initial_root_sha256": initial_digest,
            "built_root_sha256": build_digest,
            "packages": package_results,
            "runtime_error": f"{type(exc).__name__}: {exc}",
            "review_required": any(item.get("review_required") for item in package_results),
        }

    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    serial_progress(f"runtime proof {payload['status']}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="execute the normalized M9 NetworkManager + IceWM proof on the booted M8 guest"
    )
    parser.add_argument("--work", type=Path, default=Path("/var/lib/distro-m8/m9-runtime/work"))
    parser.add_argument("--cache", type=Path, default=Path("/var/cache/distro-lfs-optimize"))
    parser.add_argument("--result", type=Path, default=Path("/var/lib/distro-m8/m9-runtime/result.json"))
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    result = run_m9(args.work, args.cache, args.result, run_tests=not args.skip_tests)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
