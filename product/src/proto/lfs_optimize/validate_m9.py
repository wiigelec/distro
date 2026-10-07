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
        == [
            ("libndp", "default"),
            ("cmake", "m9-minimal"),
            ("networkmanager", "default"),
            ("icewm", "default"),
        ],
        "M9 package/build identity or order drift",
    )

    libndp, cmake, networkmanager, icewm = resolved["packages"]

    require(
        "NetworkManager" in libndp["dependencies"]["before"],
        "libndp -> NetworkManager ordering relationship missing",
    )
    require(
        "libndp" in networkmanager["dependencies"]["build"],
        "NetworkManager libndp requirement missing",
    )
    require(
        "systemd" in networkmanager["dependencies"]["runtime"],
        "NetworkManager systemd runtime relationship missing",
    )
    require(
        networkmanager["integration"]["network_management"]["manager"] == "NetworkManager"
        and "systemd-networkd"
        in networkmanager["integration"]["network_management"]["exclusive_with"],
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

    plan = plan_blfs(
        run_tests=True,
        versions_path=VERSIONS,
        package_set_path=PACKAGE_SET,
    )
    cmake_commands = plan["packages"][1]["commands"]
    nm_commands = plan["packages"][2]["commands"]
    icewm_commands = plan["packages"][3]["commands"]

    required_bundled = (
        "--no-system-curl",
        "--no-system-libarchive",
        "--no-system-libuv",
        "--no-system-nghttp2",
    )
    require(
        any(
            all(flag in item["command"] for flag in required_bundled)
            for item in cmake_commands
        ),
        "M9 CMake bundled-dependency build policy missing",
    )

    require(
        any(
            "-D session_tracking=systemd" in item["command"]
            and "-D nmtui=true" in item["command"]
            for item in nm_commands
        ),
        "NetworkManager reference build policy missing",
    )
    require(
        any(
            "/etc/NetworkManager/NetworkManager.conf" in item["command"]
            and "plugins=keyfile" in item["command"]
            for item in nm_commands
        ),
        "NetworkManager base configuration missing",
    )
    require(
        any(
            item.get("kind") == "session-transition"
            and item["command"] == "systemctl enable NetworkManager"
            for item in nm_commands
        ),
        "NetworkManager service enable transition missing",
    )
    require(
        any("ENABLE_LTO=ON" in item["command"] for item in icewm_commands),
        "IceWM required LTO build option missing",
    )
    require(
        any(
            item["command"] == "rm -v /usr/share/xsessions/icewm.desktop"
            for item in icewm_commands
        ),
        "IceWM duplicate X session cleanup missing",
    )

    print("M9 ordinary dependency frontier proof: success")
    print("libndp and CMake are explicit; Xorg collection semantics remain the next frontier.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
