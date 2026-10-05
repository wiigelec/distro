#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from resolve import HERE, resolve

PRESENTATION = HERE / "presentation"
FORBIDDEN_EDITORIAL_KEYS = {
    "version",
    "source",
    "resources",
    "procedure",
    "dependencies",
    "installed",
    "installed_descriptions",
    "document",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_presentation(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise RuntimeError(f"unsupported presentation schema: {path}")
    return value


def package_inputs(
    name: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    structure = load_presentation(PRESENTATION / "structure.json")
    editorial = load_presentation(PRESENTATION / "editorial" / f"{name}.json")

    require(editorial.get("package") == name, f"{name}: editorial package mismatch")
    forbidden = sorted(FORBIDDEN_EDITORIAL_KEYS.intersection(editorial))
    require(
        not forbidden,
        f"{name}: editorial duplicates authoritative data: {', '.join(forbidden)}",
    )

    packages = structure.get("packages")
    require(
        isinstance(packages, list),
        "presentation structure packages must be a list",
    )
    entry = next((item for item in packages if item.get("name") == name), None)
    require(isinstance(entry, dict), f"{name}: missing presentation structure")
    require(
        entry.get("sections") == ["summary", "source", "installation", "contents"],
        f"{name}: unsupported presentation section composition",
    )

    resolved = resolve([name])["packages"][0]
    return resolved, entry, editorial


def add_text(
    parent: ET.Element,
    tag: str,
    value: str,
    **attrs: str,
) -> ET.Element:
    node = ET.SubElement(parent, tag, attrs)
    node.text = value
    return node


def render_package(name: str) -> str:
    package, structure, editorial = package_inputs(name)
    document = package["document"]

    root = ET.Element("section", {"xml:id": document["section_id"]})
    add_text(root, "title", f"{structure['title']} {package['version']}")

    summary = ET.SubElement(root, "sect2", {"role": "summary"})
    add_text(summary, "title", editorial["summary_title"])
    add_text(
        summary,
        "para",
        package["description"],
        role="package-description",
    )

    source = ET.SubElement(root, "sect2", {"role": "source"})
    add_text(source, "title", editorial["source_title"])
    variable = ET.SubElement(source, "variablelist")
    for label, role, value in (
        ("Download", "source-url", package["source"]["url"]),
        ("MD5 sum", "source-md5", package["source"]["md5"]),
        ("Download size", "source-size", package["source"]["size"]),
        ("Home page", "source-home", package["source"]["home"]),
    ):
        entry = ET.SubElement(variable, "varlistentry")
        add_text(entry, "term", label)
        item = ET.SubElement(entry, "listitem")
        add_text(item, "para", value, role=role)

    install = ET.SubElement(root, "sect2", {"role": "installation"})
    add_text(install, "title", editorial["installation_title"])
    intros = editorial.get("phase_intros", {})
    for step in package["procedure"]:
        phase = step["phase"]
        phase_node = ET.SubElement(install, "sect3", {"role": phase})
        add_text(phase_node, "title", phase.replace("-", " ").title())
        intro = intros.get(phase)
        if intro:
            add_text(phase_node, "para", intro)
        screen = ET.SubElement(phase_node, "screen")
        for command in step["commands"]:
            add_text(
                screen,
                "userinput",
                command["command"],
                role="build-command",
                condition=step["condition"],
                user=command["user"],
            )

    contents = ET.SubElement(
        root,
        "sect2",
        {
            "xml:id": document["contents_id"],
            "role": "contents",
        },
    )
    add_text(contents, "title", editorial["contents_title"])
    table = ET.SubElement(contents, "variablelist")
    for item in package["installed_descriptions"]:
        entry = ET.SubElement(
            table,
            "varlistentry",
            {"xml:id": item["id"]},
        )
        add_text(
            entry,
            "term",
            item["name"],
            role="installed-name",
        )
        listitem = ET.SubElement(entry, "listitem")
        add_text(
            listitem,
            "para",
            item["description"],
            role="installed-description",
        )

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def self_test() -> None:
    package, _, _ = package_inputs("zlib")
    root = ET.fromstring(render_package("zlib"))

    xml_id = "{http://www.w3.org/XML/1998/namespace}id"
    require(
        root.attrib.get(xml_id) == package["document"]["section_id"],
        "presentation section identity drift",
    )
    require(
        package["version"] in (root.findtext("title") or ""),
        "presentation version did not come from resolved state",
    )

    roles: dict[str, list[str]] = {}
    for node in root.iter():
        role = node.attrib.get("role")
        if role and node.text:
            roles.setdefault(role, []).append(node.text)

    require(
        roles.get("source-url") == [package["source"]["url"]],
        "source URL drift",
    )
    require(
        roles.get("source-md5") == [package["source"]["md5"]],
        "source checksum drift",
    )

    rendered_commands = roles.get("build-command", [])
    expected_commands = [
        command["command"]
        for step in package["procedure"]
        for command in step["commands"]
    ]
    require(
        rendered_commands == expected_commands,
        "procedure command drift",
    )

    rendered_installed = roles.get("installed-name", [])
    expected_installed = [
        item["name"] for item in package["installed_descriptions"]
    ]
    require(
        rendered_installed == expected_installed,
        "installed-content drift",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="compile normalized LFS presentation proof"
    )
    parser.add_argument("--package", default="zlib")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    try:
        if args.self_test:
            self_test()
            print(
                json.dumps(
                    {
                        "status": "success",
                        "milestone": "presentation-slice",
                        "package": "zlib",
                    },
                    indent=2,
                )
            )
            return 0

        rendered = render_package(args.package)
    except RuntimeError as exc:
        parser.error(str(exc))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
