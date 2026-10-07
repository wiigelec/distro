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

    expected = [
        ("libndp", "default"),
        ("cmake", "m9-minimal"),
        ("networkmanager", "default"),
        *[(name, "collection:xorg-libraries") for name in XORG_LIBRARY_MEMBERS],
        ("icewm", "default"),
    ]
    require(
        [(p["name"], p["build"]) for p in resolved["packages"]] == expected,
        "M9 package/build/collection identity or order drift",
    )

    require(
        resolved["collections"]
        == [{
            "name": "xorg-libraries",
            "members": XORG_LIBRARY_MEMBERS,
            "dependencies": {
                "build": ["fontconfig", "libxcb"],
                "runtime": ["dbus"],
                "test": [],
                "before": [],
                "recommended": [],
                "optional": ["asciidoc", "xmlto", "fop", "Links", "Lynx", "ncompress", "W3m"],
            },
        }],
        "Xorg Libraries collection metadata drift",
    )

    by_name = {package["name"]: package for package in resolved["packages"]}
    require(
        by_name["libX11"]["collection_member_index"] == 1
        and by_name["libXpresent"]["collection_member_index"] == len(XORG_LIBRARY_MEMBERS) - 1,
        "Xorg Libraries collection order metadata missing",
    )

    def command(package: str, needle: str) -> bool:
        return any(
            needle in item["command"]
            for phase in by_name[package]["procedure"]
            for item in phase["commands"]
        )

    require(command("libX11", "--disable-static"), "shared Xorg library procedure missing")
    require(
        command("libXfont2", "--disable-devel-docs"),
        "libXfont2 collection override missing",
    )
    require(
        command("libXt", "--with-appdefaultdir=/etc/X11/app-defaults"),
        "libXt collection override missing",
    )
    require(
        command("libXpm", "--disable-open-zfile"),
        "libXpm collection override missing",
    )
    require(
        command("libpciaccess", "meson setup --prefix=/usr")
        and command("libxkbfile", "ninja -C build"),
        "Meson Xorg library collection override missing",
    )

    libndp = by_name["libndp"]
    networkmanager = by_name["networkmanager"]
    icewm = by_name["icewm"]
    require(
        "NetworkManager" in libndp["dependencies"]["before"]
        and "libndp" in networkmanager["dependencies"]["build"],
        "NetworkManager ordinary dependency frontier drift",
    )
    require(
        "CMake" in icewm["dependencies"]["build"]
        and "imlib2" in icewm["dependencies"]["build"],
        "IceWM ordinary dependency frontier drift",
    )

    plan = plan_blfs(
        run_tests=True,
        versions_path=VERSIONS,
        package_set_path=PACKAGE_SET,
    )
    require(
        plan["collections"][0]["members"] == XORG_LIBRARY_MEMBERS,
        "planned Xorg collection membership drift",
    )
    require(
        len(plan["packages"]) == len(expected),
        "planned M9 package count drift",
    )

    print("M9 Xorg Libraries collection model proof: success")
    print("32 members resolve in collection authority order with shared procedure and explicit overrides.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
