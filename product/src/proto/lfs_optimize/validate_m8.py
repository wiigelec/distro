#!/usr/bin/env python3
from __future__ import annotations

from blfs import plan_blfs, resolve_blfs


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def main() -> int:
    resolved = resolve_blfs()
    require(
        [(p["name"], p["build"]) for p in resolved["packages"]]
        == [("linux-pam", "default"), ("systemd", "blfs-pam")],
        "PAM/systemd build identity drift",
    )

    pam, systemd = resolved["packages"]
    require(
        pam["kernel_requirements"][0]["symbol"] == "AUDIT"
        and pam["kernel_requirements"][0]["state"] == "enabled",
        "Linux-PAM CONFIG_AUDIT requirement missing",
    )
    require(
        any(
            item.get("package") == "systemd"
            and item.get("build") == "blfs-pam"
            and item.get("action") == "rebuild-reconfigure"
            for item in pam["integration"]["post_install"]
        ),
        "Linux-PAM -> systemd rebuild integration missing",
    )

    plan = plan_blfs(run_tests=True)
    systemd_plan = plan["packages"][1]
    commands = systemd_plan["commands"]
    require(
        any(
            "-D pam=enabled" in item["command"]
            and "-D pamconfdir=/etc/pam.d" in item["command"]
            for item in commands
        ),
        "systemd PAM build flags missing",
    )
    require(
        any(
            item.get("kind") == "session-transition"
            and item["command"] == "systemctl daemon-reexec"
            for item in commands
        ),
        "systemd daemon-reexec transition missing",
    )
    print("M8 PAM/systemd model proof: success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
