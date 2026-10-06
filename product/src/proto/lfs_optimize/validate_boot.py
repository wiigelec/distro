#!/usr/bin/env python3
from __future__ import annotations

from boot import boot_plan
from resolve import HERE, load_json


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def main() -> int:
    plan = boot_plan()
    operations = load_json(HERE / "system-operations-13.1.json")["operations"]

    require(plan["basis"] == "LFS 13.1-systemd", "boot basis drift")
    for operation in plan["authority"]["system_operations"]:
        require(operation in operations, f"missing boot authority operation: {operation}")

    kernel = plan["kernel"]
    require(kernel["version"] == "7.1.8", "kernel version drift")
    require(
        kernel["source"]["url"].endswith("/linux-7.1.8.tar.xz")
        and kernel["source"]["md5"] == "807584f564568b40162e9e4a72bf191f",
        "kernel source identity drift",
    )

    required = set(kernel["required_builtin"])
    for symbol in {
        "AUDIT","DEVTMPFS","DEVTMPFS_MOUNT","EXT4_FS",
        "SERIAL_8250_CONSOLE","VIRTIO","VIRTIO_BLK","VIRTIO_PCI"
    }:
        require(symbol in required, f"boot kernel missing required built-in: {symbol}")

    require(
        plan["qemu"]["root_device"] == "/dev/vda"
        and plan["qemu"]["console"] == "ttyS0",
        "QEMU boot contract drift",
    )
    require(
        plan["proof"]["marker"] == "DISTRO_BOOT_PROOF_OK"
        and plan["proof"]["expected_pid1"] == "systemd"
        and plan["proof"]["target"] == "multi-user.target",
        "boot proof marker/PID1 contract drift",
    )

    print("booted LFS QEMU plan proof: success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
