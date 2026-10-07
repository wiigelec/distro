#!/usr/bin/env python3
from __future__ import annotations

from blfs import plan_blfs, resolve_blfs
from resolve import HERE

VERSIONS = HERE / "versions" / "m9-development.json"
PACKAGE_SET = HERE / "m9-package-set.json"
XORG_LIBRARY_MEMBERS = ['xtrans', 'libX11', 'libXext', 'libFS', 'libICE', 'libSM', 'libXScrnSaver', 'libXt', 'libXmu', 'libXpm', 'libXaw', 'libXfixes', 'libXcomposite', 'libXrender', 'libXcursor', 'libXdamage', 'libfontenc', 'libXfont2', 'libXft', 'libXi', 'libXinerama', 'libXrandr', 'libXres', 'libXtst', 'libXv', 'libXvMC', 'libXxf86dga', 'libXxf86vm', 'libpciaccess', 'libxkbfile', 'libxshmfence', 'libXpresent']

def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)

def main() -> int:
    resolved = resolve_blfs(VERSIONS, PACKAGE_SET)
    by_name = {p["name"]: p for p in resolved["packages"]}

    names = [p["name"] for p in resolved["packages"]]
    collection_start = names.index(XORG_LIBRARY_MEMBERS[0])
    server_index = names.index("xorg-server")
    require(
        names[collection_start:collection_start + len(XORG_LIBRARY_MEMBERS)]
        == XORG_LIBRARY_MEMBERS,
        "Xorg Libraries collection order drift",
    )
    require(
        all(names.index(name) < collection_start for name in ("fontconfig", "libxcb")),
        "Xorg Libraries prerequisites must precede the collection",
    )
    require(
        all(names.index(name) < server_index for name in ("libxcvt", "pixman", "font-util", "xkeyboard-config")),
        "Xorg Server prerequisites must precede the server",
    )

    server = by_name["xorg-server"]
    require(server["build"] == "m9-xvfb", "M9 must select the headless Xorg Server build")
    require(
        server["dependencies"]["build"]
        == ["xorg-libraries", "libxcvt", "pixman", "font-util"],
        "Xorg Server build dependency closure drift",
    )
    require(
        server["dependencies"]["runtime"] == ["xkeyboard-config", "systemd"],
        "Xorg Server runtime dependency closure drift",
    )

    commands = [
        item["command"]
        for phase in server["procedure"]
        for item in phase["commands"]
    ]
    require(
        any("-D glamor=false" in command and "-D secure-rpc=false" in command for command in commands),
        "M9 Xvfb build policy missing",
    )
    require(
        not any("tearfree_backport" in command for command in commands),
        "headless Xvfb build must not apply the graphical TearFree patch",
    )
    require("Xvfb" in server["installed"]["programs"], "Xvfb installed-content claim missing")
    require(server["installed"]["libraries"] == [], "M9 Xvfb build must not claim modesetting_drv")

    require(
        by_name["xkeyboard-config"]["dependencies"]["build"] == ["xorg-libraries"],
        "xkeyboard-config Xorg library requirement missing",
    )
    require(
        by_name["libxcvt"]["dependencies"]["build"] == ["xorg-libraries"],
        "libxcvt Xorg build environment requirement missing",
    )

    plan = plan_blfs(
        run_tests=True,
        versions_path=VERSIONS,
        package_set_path=PACKAGE_SET,
    )
    planned = {p["package"]: p for p in plan["packages"]}
    require("xorg-server" in planned, "planned Xorg Server missing")
    require(
        any("-D glamor=false" in item["command"] for item in planned["xorg-server"]["commands"]),
        "planned Xorg Server did not preserve M9 build policy",
    )

    print("M9 Xorg Server headless runtime closure proof: success")
    print("Xvfb is selected without Mesa/Glamor; xkeyboard-config and PAM-enabled systemd remain runtime requirements.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
