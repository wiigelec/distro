#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from resolve import HERE, resolve

PRESENTATION = HERE / "presentation"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
FORBIDDEN_EDITORIAL_KEYS = {
    "version",
    "source",
    "resources",
    "reference_metrics",
    "procedure",
    "dependencies",
    "installed",
    "installed_descriptions",
    "document",
}

INSTALLED_CATEGORY_LABELS = (
    ("programs", "Installed programs"),
    ("libraries", "Installed libraries"),
    ("directories", "Installed directories"),
)


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
        entry.get("sections") == ["package", "installation", "contents"],
        f"{name}: unsupported presentation section composition",
    )

    document = entry.get("document")
    require(isinstance(document, dict), f"{name}: missing presentation document identity")
    for field in ("section_id", "filename", "contents_id"):
        require(
            isinstance(document.get(field), str) and document[field],
            f"{name}: missing presentation document {field}",
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


def render_metrics(parent: ET.Element, package: dict[str, Any]) -> None:
    metrics = package.get("reference_metrics")
    require(isinstance(metrics, dict), f"{package['name']}: missing reference metrics")
    require(
        isinstance(metrics.get("build_time"), str) and metrics["build_time"],
        f"{package['name']}: missing reference build time",
    )
    require(
        isinstance(metrics.get("disk_space"), str) and metrics["disk_space"],
        f"{package['name']}: missing reference disk space",
    )

    segmented = ET.SubElement(parent, "segmentedlist", {"role": "reference-metrics"})
    add_text(segmented, "segtitle", "Approximate build time")
    add_text(segmented, "segtitle", "Required disk space")
    item = ET.SubElement(segmented, "seglistitem")
    add_text(item, "seg", metrics["build_time"], role="build-time")
    add_text(item, "seg", metrics["disk_space"], role="disk-space")


def command_anchor(phase: str, command_index: int) -> str:
    return f"{phase}:{command_index}"


def command_remap(phase: str) -> str:
    return {
        "build": "make",
    }.get(phase, phase)


def render_installation(
    root: ET.Element,
    package: dict[str, Any],
    editorial: dict[str, Any],
) -> None:
    install = ET.SubElement(root, "sect2", {"role": "installation"})
    add_text(install, "title", editorial["installation_title"])

    intros = editorial.get("command_intros")
    require(
        isinstance(intros, dict),
        f"{package['name']}: command_intros must be an object",
    )

    seen: set[str] = set()
    for step in package["procedure"]:
        phase = step["phase"]
        for command_index, command in enumerate(step["commands"]):
            anchor = command_anchor(phase, command_index)
            intro = intros.get(anchor)
            require(
                isinstance(intro, str) and intro,
                f"{package['name']}: missing editorial intro for {anchor}",
            )
            seen.add(anchor)
            add_text(
                install,
                "para",
                intro,
                role="command-intro",
                anchor=anchor,
            )
            screen = ET.SubElement(install, "screen", {"format": "linespecific"})
            add_text(
                screen,
                "userinput",
                command["command"],
                role="build-command",
                anchor=anchor,
                remap=command_remap(phase),
                condition=step["condition"],
                user=command["user"],
            )

    extra = sorted(set(intros) - seen)
    require(
        not extra,
        f"{package['name']}: editorial command intro has no authoritative command: "
        + ", ".join(extra),
    )


def render_installed_summary(parent: ET.Element, package: dict[str, Any]) -> None:
    installed = package.get("installed")
    require(isinstance(installed, dict), f"{package['name']}: missing installed summary")

    present = [
        (key, label, installed[key])
        for key, label in INSTALLED_CATEGORY_LABELS
        if key in installed and installed[key]
    ]
    require(present, f"{package['name']}: empty installed summary")

    segmented = ET.SubElement(parent, "segmentedlist", {"role": "installed-summary"})
    for _, label, _ in present:
        add_text(segmented, "segtitle", label)
    item = ET.SubElement(segmented, "seglistitem")
    for key, _, values in present:
        require(
            isinstance(values, list)
            and all(isinstance(value, str) and value for value in values),
            f"{package['name']}: invalid installed {key}",
        )
        add_text(
            item,
            "seg",
            ", ".join(values),
            role=f"installed-{key}",
        )


def render_installed_term(
    parent: ET.Element,
    item: dict[str, Any],
    kind: str,
) -> None:
    if kind == "program":
        add_text(parent, "command", item["name"], role="installed-name")
    elif kind == "library":
        add_text(
            parent,
            "filename",
            item["name"],
            role="installed-name",
            **{"class": "libraryfile"},
        )
    else:
        add_text(parent, "filename", item["name"], role="installed-name")


def render_contents(
    root: ET.Element,
    package: dict[str, Any],
    structure: dict[str, Any],
    editorial: dict[str, Any],
) -> None:
    document = structure["document"]
    contents = ET.SubElement(
        root,
        "sect2",
        {
            XML_ID: document["contents_id"],
            "role": "content",
        },
    )
    add_text(contents, "title", editorial["contents_title"])
    render_installed_summary(contents, package)

    variable = ET.SubElement(contents, "variablelist")
    add_text(variable, "bridgehead", "Short Descriptions", renderas="sect3")

    item_kinds = structure.get("installed_item_kinds", {})
    require(
        isinstance(item_kinds, dict),
        f"{package['name']}: installed_item_kinds must be an object",
    )

    seen: set[str] = set()
    for item in package["installed_descriptions"]:
        item_id = item["id"]
        kind = item_kinds.get(item_id)
        require(
            kind in ("program", "library", "file"),
            f"{package['name']}: missing installed presentation kind for {item_id}",
        )
        seen.add(item_id)
        entry = ET.SubElement(variable, "varlistentry", {XML_ID: item_id})
        term = ET.SubElement(entry, "term")
        render_installed_term(term, item, kind)
        listitem = ET.SubElement(entry, "listitem")
        add_text(
            listitem,
            "para",
            item["description"],
            role="installed-description",
        )

    extra = sorted(set(item_kinds) - seen)
    require(
        not extra,
        f"{package['name']}: installed presentation kind has no authoritative item: "
        + ", ".join(extra),
    )


def render_package(name: str) -> str:
    package, structure, editorial = package_inputs(name)
    document = structure["document"]

    root = ET.Element(
        "sect1",
        {
            XML_ID: document["section_id"],
            "role": "wrap",
        },
    )
    add_text(root, "title", f"{structure['title']}-{package['version']}")

    summary = ET.SubElement(root, "sect2", {"role": "package"})
    ET.SubElement(summary, "title")
    add_text(
        summary,
        "para",
        package["description"],
        role="package-description",
    )
    render_metrics(summary, package)

    render_installation(root, package, editorial)
    render_contents(root, package, structure, editorial)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def collect_roles(root: ET.Element) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {}
    for node in root.iter():
        role = node.attrib.get("role")
        if role and node.text:
            roles.setdefault(role, []).append(node.text)
    return roles


def self_test() -> None:
    package, structure, editorial = package_inputs("zlib")
    root = ET.fromstring(render_package("zlib"))
    roles = collect_roles(root)

    require(root.tag == "sect1", "presentation root hierarchy drift")
    require(root.attrib.get("role") == "wrap", "presentation root role drift")
    require(
        root.attrib.get(XML_ID) == structure["document"]["section_id"],
        "presentation section identity drift",
    )
    require(
        root.findtext("title") == f"{structure['title']}-{package['version']}",
        "presentation title/version drift",
    )
    require(
        [child.attrib.get("role") for child in root.findall("sect2")]
        == ["package", "installation", "content"],
        "presentation visible section hierarchy drift",
    )

    metrics = package["reference_metrics"]
    require(
        roles.get("build-time") == [metrics["build_time"]],
        "reference build-time drift",
    )
    require(
        roles.get("disk-space") == [metrics["disk_space"]],
        "reference disk-space drift",
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

    expected_intros = []
    for step in package["procedure"]:
        for command_index, _ in enumerate(step["commands"]):
            expected_intros.append(
                editorial["command_intros"][command_anchor(step["phase"], command_index)]
            )
    require(
        roles.get("command-intro") == expected_intros,
        "command editorial ordering drift",
    )

    installed = package["installed"]
    require(
        roles.get("installed-libraries") == [", ".join(installed["libraries"])],
        "installed-library summary drift",
    )

    rendered_installed = roles.get("installed-name", [])
    expected_installed = [
        item["name"] for item in package["installed_descriptions"]
    ]
    require(
        rendered_installed == expected_installed,
        "installed-content drift",
    )

    require(
        roles.get("installed-description")
        == [item["description"] for item in package["installed_descriptions"]],
        "installed-description drift",
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
                        "equivalence": "visible-semantic-structure",
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
