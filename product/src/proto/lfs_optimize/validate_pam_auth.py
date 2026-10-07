#!/usr/bin/env python3
from __future__ import annotations

from pam_auth import AUTH_MARKER_OK, auth_plan


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def main() -> int:
    plan = auth_plan()
    require(plan["kind"] == "booted-pam-login-proof", "auth proof kind drift")
    require(plan["input"] == "successful booted BLFS guest image", "auth proof input drift")
    require(
        plan["authentication_path"] == "/usr/bin/login on a controlling PTY",
        "authentication path drift",
    )
    require(plan["caller"] == "unprivileged nobody user", "login caller drift")
    require(plan["test_user"] == "disposable local account", "test-account contract drift")
    require(
        plan["session_proof"] == "authenticated login shell reports expected UID and user",
        "session proof drift",
    )
    require(plan["cleanup"] == "test account removed before shutdown", "cleanup contract drift")
    require(plan["success_marker"] == AUTH_MARKER_OK, "auth success marker drift")
    print("booted PAM login/session plan proof: success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
