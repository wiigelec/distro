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
    prefix = [
        ("libndp", "default"),
        ("cmake", "m9-minimal"),
        ("networkmanager", "default"),
        ("freetype2", "m9-bootstrap"),
        ("fontconfig", "default"),
        ("util-macros", "default"),
        ("xorgproto", "default"),
        ("libXau", "default"),
        ("libXdmcp", "default"),
        ("xcb-proto", "default"),
        ("libxcb", "default"),
    ]
    expected = [
        *prefix,
        *[(name, "collection:xorg-libraries") for name in XORG_LIBRARY_MEMBERS],
        ("icewm", "default"),
    ]
    require(
        [(p["name"], p["build"]) for p in resolved["packages"]] == expected,
        "M9 prerequisite/collection identity or order drift",
    )

    require(
        resolved["collections"]
        == [{
            "name": "xorg-libraries",
            "members": XORG_LIBRARY_MEMBERS,
            "dependencies": {
                "build": ["fontconfig", "libxcb"],
                "runtime": [],
                "test": [],
                "before": [],
                "recommended": [],
                "optional": ["asciidoc", "xmlto", "fop", "Links", "Lynx", "ncompress", "W3m"],
            },
        }],
        "Xorg Libraries collection dependency metadata drift",
    )

    by_name = {p["name"]: p for p in resolved["packages"]}
    require(
        by_name["freetype2"]["build"] == "m9-bootstrap"
        and any(
            "--without-harfbuzz" in item["command"]
            for phase in by_name["freetype2"]["procedure"]
            for item in phase["commands"]
        ),
        "M9 FreeType bootstrap build policy missing",
    )
    require(
        by_name["fontconfig"]["dependencies"]["build"] == ["freetype2"],
        "Fontconfig -> FreeType dependency missing",
    )
    require(
        by_name["xorgproto"]["dependencies"]["build"] == ["util-macros"],
        "xorgproto -> util-macros dependency missing",
    )
    require(
        by_name["libXau"]["dependencies"]["build"] == ["xorgproto"]
        and by_name["libXdmcp"]["dependencies"]["build"] == ["xorgproto"],
        "X authorization/display-manager protocol prerequisite drift",
    )
    require(
        by_name["libxcb"]["dependencies"]["build"] == ["libXau", "xcb-proto"]
        and "libXdmcp" in by_name["libxcb"]["dependencies"]["recommended"],
        "libxcb prerequisite closure missing",
    )

    def command(package: str, needle: str) -> bool:
        return any(
            needle in item["command"]
            for phase in by_name[package]["procedure"]
            for item in phase["commands"]
        )

    require(command("libX11", "--disable-static"), "shared Xorg library procedure missing")
    require(command("libXfont2", "--disable-devel-docs"), "libXfont2 override missing")
    require(command("libXt", "--with-appdefaultdir=/etc/X11/app-defaults"), "libXt override missing")
    require(command("libXpm", "--disable-open-zfile"), "libXpm override missing")
    require(
        command("libpciaccess", "meson setup --prefix=/usr")
        and command("libxkbfile", "ninja -C build"),
        "Meson collection overrides missing",
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
    require(len(plan["packages"]) == len(expected), "planned M9 package count drift")

    print("M9 Xorg Libraries prerequisite closure proof: success")
    print("Collection prerequisites resolve explicitly before the 32-member executable collection.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
