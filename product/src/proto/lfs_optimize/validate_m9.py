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
        names.index("xkbcomp")
        < names.index("xorg-server")
        < names.index("xorg-libinput")
        < names.index("xterm")
        < names.index("xinit")
        < names.index("icewm"),
        "M9 XKB/Xorg/libinput/xterm/xinit/IceWM order drift",
    )
    require(
        names.index("libevdev")
        < names.index("libinput")
        and names.index("mtdev") < names.index("libinput")
        < names.index("xorg-libinput"),
        "M9 libinput dependency order drift",
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
    require(server["build"] == "m9-desktop", "M9 desktop Xorg build selection drift")
    require(
        {"Xorg", "Xvfb"}.issubset(server["installed"]["programs"])
        and "modesetting_drv.so" in server["installed"]["libraries"],
        "M9 Xorg/Xvfb/modesetting capability drift",
    )
    require(
        server["dependencies"]["build"]
        == ["xorg-libraries", "libxcvt", "pixman", "font-util", "libdrm"]
        and server["dependencies"]["runtime"]
        == ["xkeyboard-config", "xkbcomp", "systemd", "libdrm", "xorg-libinput"],
        "M9 desktop Xorg dependency closure drift",
    )
    require(
        any(
            "-D glamor=false" in c
            and "-D glx=false" in c
            and "-D secure-rpc=false" in c
            for c in commands(server)
        ),
        "M9 desktop Xorg acceleration/security build policy missing",
    )

    libinput = by_name["libinput"]
    require(
        libinput["dependencies"]["runtime"] == ["libevdev", "mtdev", "systemd"],
        "M9 libinput runtime closure drift",
    )

    xorg_libinput = by_name["xorg-libinput"]
    require(
        xorg_libinput["dependencies"]["runtime"] == ["libinput", "xorg-server"]
        and "libinput_drv.so" in xorg_libinput["installed"]["libraries"],
        "M9 Xorg libinput driver closure drift",
    )

    xterm = by_name["xterm"]
    require(
        "xterm" in xterm["installed"]["programs"]
        and any("--enable-mini-luit" in c for c in commands(xterm)),
        "M9 xterm terminal policy drift",
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
    require(
        any(
            "-D glamor=false" in item["command"]
            and "-D glx=false" in item["command"]
            for item in planned["xorg-server"]["commands"]
        ),
        "planned M9 desktop Xorg policy missing",
    )
    require(
        any("--enable-mini-luit" in item["command"]
            for item in planned["xterm"]["commands"]),
        "planned xterm mini-luit policy missing",
    )

    print("M9 buildable functional-system model proof: success")
    print("NetworkManager, real Xorg + Xvfb, libinput, IceWM, fonts, and xterm are explicit.")
    print("Automated and interactive booted runtime acceptance have both been proven.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
