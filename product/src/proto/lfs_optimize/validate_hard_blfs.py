#!/usr/bin/env python3
from __future__ import annotations

from blfs import (
    enabled_collection_members,
    load_collection,
    package_set_entry,
    resolve_blfs,
)
from presentation import PRESENTATION, load_presentation
from resolve import HERE, load_json, resolve

VERSIONS = HERE / "versions" / "m9-development.json"
PACKAGE_SET = HERE / "m9-package-set.json"
COLLECTION = "xorg-libraries"
KDE_COLLECTION = "kde-frameworks"
KDE_VERSIONS = HERE / "versions" / "hard-blfs-development.json"
KDE_PACKAGE_SET = HERE / "hard-blfs-package-set.json"


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def commands(package: dict) -> list[str]:
    return [
        command["command"]
        for step in package["procedure"]
        for command in step["commands"]
    ]


def main() -> int:
    definition = load_collection(COLLECTION)
    members = enabled_collection_members(definition)
    member_names = [member["name"] for member in members]

    require(
        len(member_names) >= 25
        and len(member_names) == len(set(member_names)),
        "Xorg collection must contain a substantial unique ordered member set",
    )
    require(
        member_names[0] == "xtrans"
        and member_names[-1] == "libXpresent",
        "Xorg collection boundary/order drift",
    )

    override_names = {
        member["name"]
        for member in members
        if "procedure" in member
    }
    require(
        {"libXt", "libXpm", "libXfont2", "libpciaccess", "libxkbfile"}
        .issubset(override_names),
        "Xorg per-member procedure overrides are incomplete",
    )

    resolved = resolve_blfs(VERSIONS, PACKAGE_SET)
    collection = next(
        (item for item in resolved["collections"] if item["name"] == COLLECTION),
        None,
    )
    require(collection is not None, "resolved M9 state lost the Xorg collection")
    require(
        collection["members"] == member_names,
        "resolved Xorg collection member order drift",
    )

    resolved_members = [
        package
        for package in resolved["packages"]
        if package.get("collection") == COLLECTION
    ]
    require(
        [package["name"] for package in resolved_members] == member_names,
        "Xorg collection expansion does not preserve explicit member order",
    )
    require(
        [package["collection_member_index"] for package in resolved_members]
        == list(range(len(member_names))),
        "Xorg collection member indexes are not stable and contiguous",
    )
    require(
        all(
            package["build"] == f"collection:{COLLECTION}"
            for package in resolved_members
        ),
        "Xorg collection build identity drift",
    )

    by_name = {package["name"]: package for package in resolved_members}

    libx11 = by_name["libX11"]
    require(
        any(
            "--docdir=/usr/share/doc/libX11-" in command
            for command in commands(libx11)
        ),
        "Xorg shared collection procedure was not inherited/substituted",
    )

    require(
        any(
            "--with-appdefaultdir=/etc/X11/app-defaults" in command
            for command in commands(by_name["libXt"])
        ),
        "libXt collection override missing",
    )
    require(
        any(
            "--disable-open-zfile" in command
            for command in commands(by_name["libXpm"])
        ),
        "libXpm collection override missing",
    )
    require(
        any(
            "--disable-devel-docs" in command
            for command in commands(by_name["libXfont2"])
        ),
        "libXfont2 collection override missing",
    )
    for name in ("libpciaccess", "libxkbfile"):
        require(
            any("meson setup" in command for command in commands(by_name[name]))
            and not any("./configure" in command for command in commands(by_name[name])),
            f"{name} must replace, not merge with, the shared collection procedure",
        )

    require(
        all(
            package["collection"] == COLLECTION
            and isinstance(package["version"], str)
            and package["version"]
            and package["source"].get("url")
            and package["source"].get("md5")
            for package in resolved_members
        ),
        "Xorg collection members must resolve independently versioned package state",
    )



    kde_definition = load_collection(KDE_COLLECTION)
    kde_members = enabled_collection_members(kde_definition)
    kde_member_names = [member["name"] for member in kde_members]
    require(
        kde_member_names
        == ["attica", "kapidox", "karchive", "kcodecs", "kconfig", "kcoreaddons"],
        "KDE Frameworks representative collection order drift",
    )
    require(
        {
            member["name"]
            for member in kde_members
            if "procedure" in member
        }
        == {"kapidox"},
        "KDE Frameworks exception set drift",
    )

    kde_resolved = resolve_blfs(KDE_VERSIONS, KDE_PACKAGE_SET)
    require(
        kde_resolved["collections"]
        == [
            {
                "name": KDE_COLLECTION,
                "members": kde_member_names,
                "dependencies": kde_definition["dependencies"],
            }
        ],
        "KDE Frameworks collection metadata drift",
    )
    kde_packages = kde_resolved["packages"]
    require(
        [package["name"] for package in kde_packages] == kde_member_names
        and [package["collection_member_index"] for package in kde_packages]
        == list(range(len(kde_member_names))),
        "KDE Frameworks collection expansion/order drift",
    )
    require(
        all(
            package["build"] == f"collection:{KDE_COLLECTION}"
            and package["version"] == "6.29.0"
            and package["source"]["url"].endswith(
                f"/{package['name']}-6.29.0.tar.xz"
            )
            and len(package["source"]["md5"]) == 32
            for package in kde_packages
        ),
        "KDE Frameworks independent source/version identity drift",
    )

    kde_by_name = {package["name"]: package for package in kde_packages}
    for name in ("attica", "karchive", "kcodecs", "kconfig", "kcoreaddons"):
        package_commands = commands(kde_by_name[name])
        require(
            any(
                "CMAKE_INSTALL_PREFIX=/usr" in command
                and "CMAKE_PREFIX_PATH=$QT6DIR" in command
                and "BUILD_TESTING=OFF" in command
                and "BUILD_PYTHON_BINDINGS=OFF" in command
                for command in package_commands
            )
            and any("make -C build" == command for command in package_commands),
            f"{name}: shared KDE Frameworks CMake procedure drift",
        )

    kapidox_commands = commands(kde_by_name["kapidox"])
    require(
        any("pip3 wheel" in command for command in kapidox_commands)
        and any("pip3 install" in command for command in kapidox_commands)
        and not any("cmake " in command for command in kapidox_commands)
        and not any("make -C build" in command for command in kapidox_commands),
        "kapidox must replace, not merge with, the shared KF6 CMake procedure",
    )

    print("Hard-BLFS KDE Frameworks collection contract: success")
    print("KF6 order, shared CMake semantics, and kapidox procedure replacement are explicit.")

    catalogs = load_presentation(PRESENTATION / "catalogs.json")
    catalog = next(
        (
            item
            for item in catalogs.get("catalogs", [])
            if item.get("name") == "python-modules"
        ),
        None,
    )
    require(isinstance(catalog, dict), "Python Modules presentation catalog missing")
    require(
        catalog.get("title") == "Python Modules"
        and catalog.get("kind") == "presentation-catalog",
        "Python Modules catalog identity drift",
    )

    catalog_members = catalog.get("members")
    require(
        catalog_members
        == [
            "jinja2",
            "markupsafe",
            "setuptools",
            "wheel",
            "packaging",
            "flit-core",
        ],
        "Python Modules presentation membership/order drift",
    )
    require(
        len(catalog_members) == len(set(catalog_members)),
        "Python Modules catalog contains duplicate members",
    )

    forbidden_catalog_keys = {
        "procedure",
        "dependencies",
        "build",
        "enabled",
        "collection",
        "before",
        "version",
        "source",
    }
    require(
        not forbidden_catalog_keys.intersection(catalog),
        "presentation catalog acquired executable package semantics",
    )

    normal_package_set = load_json(HERE / "package-set.json")["packages"]
    normal_positions = [normal_package_set.index(name) for name in catalog_members]
    require(
        normal_positions != sorted(normal_positions),
        "catalog order accidentally duplicates authoritative package execution order",
    )

    resolved_catalog_members = [resolve([name])["packages"][0] for name in catalog_members]
    require(
        [package["name"] for package in resolved_catalog_members] == catalog_members
        and all("collection" not in package for package in resolved_catalog_members)
        and all("collection_member_index" not in package for package in resolved_catalog_members),
        "presentation catalog changed independent package identity",
    )

    try:
        package_set_entry({"catalog": "python-modules"})
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "BLFS package-set parser must reject presentation catalogs as executable input"
        )

    print("Hard-BLFS presentation-catalog contract: success")
    print("Python Modules is presentation-only and does not own build order or procedure semantics.")

    print("Hard-BLFS executable-collection contract: success")
    print("Xorg collection order, shared semantics, per-member overrides, and independent versions are explicit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
