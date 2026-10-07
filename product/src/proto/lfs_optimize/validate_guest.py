#!/usr/bin/env python3
from __future__ import annotations

from guest import GUEST_MARKER_OK, guest_plan


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def main() -> int:
    plan = guest_plan()
    packages = plan["packages"]
    require(plan["execution_mode"] == "live-systemd-guest", "guest execution mode drift")
    require(plan["success_marker"] == GUEST_MARKER_OK, "guest marker drift")
    require(plan["session_transitions_execute_live"] is True, "live transition contract drift")
    require(plan["manual_checks_are_review_evidence"] is True, "manual-check contract drift")
    require(plan["tests"].startswith("disabled"), "live test isolation must remain explicit")
    require(
        [(x["name"], x["build"]) for x in packages]
        == [
            ("linux-pam", "default"),
            ("shadow", "blfs-pam"),
            ("systemd", "blfs-pam"),
        ],
        "M8 live package/build order drift",
    )
    print("booted BLFS guest execution plan proof: success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
