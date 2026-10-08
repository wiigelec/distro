#!/usr/bin/env python3
from __future__ import annotations

from blfs import resolve_blfs
from profile import FORBIDDEN_PROFILE_KEYS, load_profile, plan_profile, resolve_profile
from resolve import HERE


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def main() -> int:
    profile = load_profile("xorg-icewm")
    require(
        profile["versions"] == "versions/m9-development.json"
        and profile["package_set"] == "m9-package-set.json",
        "xorg-icewm profile must select existing validated M9 state",
    )
    require(
        not FORBIDDEN_PROFILE_KEYS.intersection(profile),
        "profile acquired package-definition authority",
    )
    require(
        profile["runtime_policy"]
        == {
            "network_manager": "NetworkManager",
            "display_server": "Xorg",
            "session": "icewm-session",
            "terminal": "xterm",
        },
        "xorg-icewm runtime policy drift",
    )

    direct = resolve_blfs(
        HERE / profile["versions"],
        HERE / profile["package_set"],
    )
    resolved = resolve_profile("xorg-icewm")
    require(
        resolved["collections"] == direct["collections"],
        "profile resolution changed collection semantics",
    )
    require(
        [
            (item["name"], item["version"], item["build"])
            for item in resolved["packages"]
        ]
        == [
            (
                package["name"],
                package["version"],
                package.get("build", "default"),
            )
            for package in direct["packages"]
        ],
        "profile resolution changed package/build/version identity",
    )

    profile_plan = plan_profile("xorg-icewm")
    require(
        profile_plan["tests_enabled"]
        and profile_plan["package_set"] == direct["package_set"]
        and profile_plan["version_manifest"] == direct["version_manifest"],
        "profile plan did not preserve selected authoritative state",
    )
    require(
        [item["package"] for item in profile_plan["packages"]]
        == [package["name"] for package in direct["packages"]],
        "profile plan changed authoritative package order",
    )
    require(
        all(item["commands"] for item in profile_plan["packages"]),
        "profile plan contains an empty package execution plan",
    )

    no_tests = plan_profile("xorg-icewm", run_tests=False)
    require(
        not no_tests["tests_enabled"]
        and [
            item["package"] for item in no_tests["packages"]
        ]
        == [item["package"] for item in profile_plan["packages"]],
        "profile test policy changed package composition/order",
    )

    print("User-system profile contract: success")
    print("xorg-icewm delegates package/collection truth to validated M9 state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
