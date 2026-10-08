#!/usr/bin/env python3
from __future__ import annotations

from blfs import plan_blfs, resolve_blfs
from resolve import HERE, load_json


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def main() -> int:
    resolved = resolve_blfs()
    require(
        [(p["name"], p["build"]) for p in resolved["packages"]]
        == [
            ("linux-pam", "default"),
            ("shadow", "blfs-pam"),
            ("systemd", "blfs-pam"),
        ],
        "PAM/Shadow/systemd build identity or order drift",
    )

    pam, shadow, systemd = resolved["packages"]

    require(
        pam["kernel_requirements"][0]["symbol"] == "AUDIT"
        and pam["kernel_requirements"][0]["state"] == "enabled",
        "Linux-PAM CONFIG_AUDIT requirement missing",
    )

    post_install = pam["integration"]["post_install"]
    require(
        any(
            item.get("package") == "shadow"
            and item.get("action") == "rebuild-reconfigure"
            and item.get("status") == "required"
            for item in post_install
        ),
        "Linux-PAM -> Shadow rebuild integration missing",
    )
    require(
        any(
            item.get("package") == "systemd"
            and item.get("build") == "blfs-pam"
            and item.get("action") == "rebuild-reconfigure"
            for item in post_install
        ),
        "Linux-PAM -> systemd rebuild integration missing",
    )

    base_shadow = load_json(HERE / "packages/shadow.json")
    base_shadow_commands = [
        command["command"]
        for step in base_shadow["procedure"]
        for command in step["commands"]
    ]
    require(
        any("/usr/sbin/pwconv" in command for command in base_shadow_commands)
        and any("/usr/sbin/grpconv" in command for command in base_shadow_commands),
        "base Shadow install must initialize /etc/shadow and /etc/gshadow",
    )

    require(
        "Linux-PAM" in shadow["dependencies"]["build"]
        and "Linux-PAM" in shadow["dependencies"]["runtime"],
        "Shadow PAM dependency missing",
    )

    plan = plan_blfs(run_tests=True)
    shadow_commands = plan["packages"][1]["commands"]
    systemd_commands = plan["packages"][2]["commands"]

    require(
        any("pamddir= install" in item["command"] for item in shadow_commands),
        "Shadow must suppress upstream PAM configuration installation",
    )
    require(
        any("/etc/pam.d/login" in item["command"] for item in shadow_commands)
        and any("/etc/pam.d/su" in item["command"] for item in shadow_commands),
        "Shadow PAM service configuration missing",
    )
    require(
        any(
            item.get("kind") == "manual-check"
            and "separate terminal" in item["command"]
            for item in shadow_commands
        ),
        "Shadow login-safety manual check missing",
    )
    require(
        any(
            "/etc/login.access" in item["command"]
            and "/etc/limits" in item["command"]
            for item in shadow_commands
        ),
        "Shadow PAM access/limits transition missing",
    )

    require(
        any(
            "-D pam=enabled" in item["command"]
            and "-D pamconfdir=/etc/pam.d" in item["command"]
            for item in systemd_commands
        ),
        "systemd PAM build flags missing",
    )
    require(
        any(
            item.get("kind") == "session-transition"
            and item["command"] == "systemctl daemon-reexec"
            for item in systemd_commands
        ),
        "systemd daemon-reexec transition missing",
    )

    print("M8 PAM/Shadow/systemd model proof: success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
