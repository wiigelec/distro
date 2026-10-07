#!/usr/bin/env python3
from __future__ import annotations

from blfs import plan_blfs, resolve_blfs
from resolve import HERE

VERSIONS = HERE / "versions" / "m9-development.json"
PACKAGE_SET = HERE / "m9-package-set.json"

def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)

def main() -> int:
    resolved = resolve_blfs(VERSIONS, PACKAGE_SET)
    by_name = {p["name"]: p for p in resolved["packages"]}
    names = [p["name"] for p in resolved["packages"]]

    require(
        names.index("xorg-server") < names.index("xinit") < names.index("icewm"),
        "xinit must resolve after the X server and before IceWM",
    )
    require(
        names.index("imlib2") < names.index("icewm"),
        "imlib2 must resolve before IceWM",
    )

    xinit = by_name["xinit"]
    require(
        xinit["dependencies"]["build"] == ["xorg-libraries"]
        and xinit["dependencies"]["runtime"] == ["xorg-server"],
        "xinit X11 dependency closure drift",
    )

    imlib2 = by_name["imlib2"]
    require(
        imlib2["dependencies"]["build"] == ["xorg-libraries"]
        and imlib2["dependencies"]["runtime"] == ["xorg-libraries"],
        "imlib2 Xorg Libraries dependency closure drift",
    )

    icewm = by_name["icewm"]
    require(
        icewm["dependencies"]["build"] == ["cmake", "imlib2", "xorg-libraries"],
        "IceWM build dependencies must be normalized package/collection identities",
    )
    require(
        icewm["dependencies"]["runtime"] == ["xorg-server"],
        "IceWM runtime X server dependency missing",
    )
    require(
        icewm["integration"]["session"]["command"] == "icewm-session"
        and icewm["integration"]["session"]["launcher"] == "xinit"
        and icewm["integration"]["graphical_environment"]["server"] == "xorg-server",
        "IceWM executable X11 session integration drift",
    )

    server = by_name["xorg-server"]
    require(server["build"] == "m9-xvfb", "M9 Xvfb build selection drift")
    require("Xvfb" in server["installed"]["programs"], "M9 Xvfb capability missing")

    plan = plan_blfs(
        run_tests=True,
        versions_path=VERSIONS,
        package_set_path=PACKAGE_SET,
    )
    planned = {p["package"]: p for p in plan["packages"]}
    require(
        any("--with-xinitdir=/etc/X11/app-defaults" in item["command"]
            for item in planned["xinit"]["commands"]),
        "xinit installation policy missing",
    )
    require(
        any("./configure --prefix=/usr --disable-static" in item["command"]
            for item in planned["imlib2"]["commands"]),
        "imlib2 build policy missing",
    )
    require(
        any("ENABLE_LTO=ON" in item["command"]
            for item in planned["icewm"]["commands"]),
        "IceWM build policy missing",
    )

    print("M9 desktop package closure proof: success")
    print("xinit, imlib2, and normalized IceWM X11 dependencies are explicit.")
    print("Only booted NetworkManager + Xvfb + IceWM runtime acceptance remains.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
