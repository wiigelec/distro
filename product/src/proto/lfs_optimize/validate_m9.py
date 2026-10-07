#!/usr/bin/env python3
from __future__ import annotations

from blfs import plan_blfs, resolve_blfs
from resolve import HERE

VERSIONS = HERE / "versions" / "m9-development.json"
PACKAGE_SET = HERE / "m9-package-set.json"

def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)

def commands(package: dict) -> list[str]:
    return [
        item["command"]
        for phase in package["procedure"]
        for item in phase["commands"]
    ]

def main() -> int:
    resolved = resolve_blfs(VERSIONS, PACKAGE_SET)
    by_name = {p["name"]: p for p in resolved["packages"]}
    names = [p["name"] for p in resolved["packages"]]

    require(
        names.index("libndp") < names.index("glib") < names.index("networkmanager"),
        "NetworkManager build prerequisites must precede NetworkManager",
    )

    glib = by_name["glib"]
    require(glib["build"] == "m9-minimal", "M9 must select the minimal GLib build")
    require(
        any(
            "-D introspection=disabled" in c
            and "-D man-pages=disabled" in c
            and "-D tests=false" in c
            and "-D sysprof=disabled" in c
            for c in commands(glib)
        ),
        "M9 GLib minimal build policy missing",
    )

    nm = by_name["networkmanager"]
    require(
        nm["build"] == "m9-wired-minimal",
        "M9 must select the wired-minimal NetworkManager build",
    )
    require(
        nm["dependencies"]["build"] == ["glib", "libndp"],
        "NetworkManager build closure must contain GLib and libndp",
    )
    require(
        nm["dependencies"]["runtime"] == ["glib", "systemd", "dbus"],
        "NetworkManager runtime closure drift",
    )
    require(
        any("-D nmtui=false" in c and "-D crypto=null" in c for c in commands(nm)),
        "NetworkManager minimal nmtui/crypto policy missing",
    )
    require(
        "nmtui" not in nm["installed"]["programs"]
        and {"NetworkManager", "nmcli", "nm-online"}.issubset(nm["installed"]["programs"]),
        "NetworkManager installed-content override drift",
    )

    require(
        names.index("xorg-server") < names.index("xinit") < names.index("icewm"),
        "xinit must resolve after Xorg Server and before IceWM",
    )
    require(names.index("imlib2") < names.index("icewm"), "imlib2 must precede IceWM")
    require(
        names.index("dejavu-fonts") < names.index("icewm"),
        "scalable font payload must precede IceWM",
    )

    fonts = by_name["dejavu-fonts"]
    require(
        fonts["dependencies"]["build"] == ["fontconfig"]
        and any("fc-cache -v /usr/share/fonts/dejavu" in c for c in commands(fonts)),
        "DejaVu/Fontconfig runtime font contract drift",
    )

    icewm = by_name["icewm"]
    require(
        icewm["dependencies"]["build"] == ["cmake", "imlib2", "xorg-libraries"],
        "IceWM normalized build dependency closure drift",
    )
    require(
        icewm["dependencies"]["runtime"] == ["xorg-server", "dejavu-fonts"],
        "IceWM runtime server/font dependency closure drift",
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
    require(
        not server.get("resources"),
        "M9 Xvfb build must not retain unused default-Xorg patch resources",
    )

    plan = plan_blfs(
        run_tests=True,
        versions_path=VERSIONS,
        package_set_path=PACKAGE_SET,
    )
    planned = {p["package"]: p for p in plan["packages"]}
    require(
        any("-D nmtui=false" in item["command"] and "-D crypto=null" in item["command"]
            for item in planned["networkmanager"]["commands"]),
        "planned NetworkManager minimal build policy missing",
    )
    require(
        any("-D tests=false" in item["command"]
            for item in planned["glib"]["commands"]),
        "planned GLib minimal build policy missing",
    )
    require(
        any("fc-cache -v /usr/share/fonts/dejavu" in item["command"]
            for item in planned["dejavu-fonts"]["commands"]),
        "planned DejaVu installation policy missing",
    )

    print("M9 buildable functional-system model proof: success")
    print("NetworkManager wired closure, Xvfb/IceWM closure, and a scalable font payload are explicit.")
    print("Booted runtime acceptance is the remaining M9 proof.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
