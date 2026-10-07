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
    require(
        [(p["name"], p["build"]) for p in resolved["packages"]]
        == [("networkmanager", "default"), ("icewm", "default")],
        "M9 target package identity or order drift",
    )
    networkmanager, icewm = resolved["packages"]

    require("libndp" in networkmanager["dependencies"]["build"],
            "NetworkManager libndp requirement missing")
    require("systemd" in networkmanager["dependencies"]["runtime"],
            "NetworkManager systemd runtime relationship missing")
    require(
        networkmanager["integration"]["network_management"]["manager"] == "NetworkManager"
        and "systemd-networkd" in networkmanager["integration"]["network_management"]["exclusive_with"],
        "NetworkManager/systemd-networkd ownership boundary missing",
    )

    require(
        "CMake" in icewm["dependencies"]["build"]
        and "imlib2" in icewm["dependencies"]["build"]
        and "graphical environment" in icewm["dependencies"]["build"],
        "IceWM graphical build prerequisites missing",
    )
    require(
        icewm["integration"]["session"]["command"] == "icewm-session"
        and icewm["integration"]["graphical_environment"]["display_protocol"] == "X11",
        "IceWM X11 session integration missing",
    )

    plan = plan_blfs(run_tests=True, versions_path=VERSIONS, package_set_path=PACKAGE_SET)
    nm_commands = plan["packages"][0]["commands"]
    icewm_commands = plan["packages"][1]["commands"]

    require(any("-D session_tracking=systemd" in x["command"] and "-D nmtui=true" in x["command"]
                for x in nm_commands),
            "NetworkManager systemd/nmtui build policy missing")
    require(any("/etc/NetworkManager/NetworkManager.conf" in x["command"]
                and "plugins=keyfile" in x["command"] for x in nm_commands),
            "NetworkManager base configuration missing")
    require(any(x.get("kind") == "session-transition"
                and x["command"] == "systemctl enable NetworkManager"
                for x in nm_commands),
            "NetworkManager service enable transition missing")
    require(any("ENABLE_LTO=ON" in x["command"] for x in icewm_commands),
            "IceWM required LTO build option missing")
    require(any(x["command"] == "rm -v /usr/share/xsessions/icewm.desktop"
                for x in icewm_commands),
            "IceWM duplicate X session cleanup missing")

    print("M9 NetworkManager/IceWM target model proof: success")
    print("Runtime acceptance remains open pending dependency closure and booted guest proof.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
