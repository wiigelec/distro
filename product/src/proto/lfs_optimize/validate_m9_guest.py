#!/usr/bin/env python3
from __future__ import annotations

from m9_guest import GUEST_MARKER_OK, guest_plan

def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)

def main() -> int:
    plan = guest_plan()
    require(plan["status"] == "success", "M9 guest plan failed")
    require(
        plan["kind"] == "booted-m9-functional-system-proof"
        and plan["base_requirement"] == "successful review-clean M8 PAM login proof image",
        "M9 guest must consume the review-clean M8 PAM acceptance image",
    )
    packages = {(item["name"], item["build"]) for item in plan["packages"]}
    for required in (
        ("glib", "m9-minimal"),
        ("networkmanager", "m9-wired-minimal"),
        ("libdrm", "default"),
        ("xorg-server", "m9-desktop"),
        ("dejavu-fonts", "default"),
        ("icewm", "default"),
    ):
        require(required in packages, f"M9 guest plan missing {required}")

    network = plan["runtime_acceptance"]["network"]
    require(
        network["manager"] == "NetworkManager"
        and network["competing_manager_inactive"] == "systemd-networkd"
        and network["requires_managed_connected_state"]
        and network["requires_ipv4_address"]
        and not network["public_internet_required"],
        "M9 NetworkManager acceptance contract drift",
    )

    desktop = plan["runtime_acceptance"]["desktop"]
    require(
        desktop["server"] == "Xvfb"
        and desktop["display"] == ":99"
        and desktop["session"] == "icewm-session"
        and desktop["process"] == "icewm"
        and desktop["requires_matching_display_environment"]
        and "DejaVu" in desktop["font"],
        "M9 IceWM acceptance contract drift",
    )
    require(
        plan["superseded_proof_units"]
        == [
            "distro-boot-proof.service",
            "distro-blfs-proof.service",
            "distro-pam-login-proof.service",
        ],
        "M9 must disable all earlier proof units before boot",
    )
    require(
        plan["cache_policy"]["host_guest_roundtrip"]
        == ["sources", "artifacts", "evidence"]
        and plan["cache_policy"]["salvage_existing_guest_before_replace"],
        "M9 guest cache persistence contract drift",
    )
    require(GUEST_MARKER_OK == "DISTRO_DESKTOP_PROOF_OK", "M9 success marker drift")

    print("M9 guest acceptance contract: success")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
