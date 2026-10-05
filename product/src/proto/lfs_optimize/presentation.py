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
PROOF_PACKAGES = ("zlib", "binutils")
FORBIDDEN_EDITORIAL_KEYS = {
    "version", "source", "resources", "reference_metrics", "procedure",
    "dependencies", "installed", "installed_descriptions", "document",
}
INLINE_TAGS = {
    "filename": "filename",
    "literal": "literal",
    "command": "command",
    "parameter": "parameter",
    "quote": "quote",
    "emphasis": "emphasis",
}

def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)

def load_presentation(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(value.get("schema_version") == 1, f"unsupported presentation schema: {path}")
    return value

def package_inputs(name: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    structure_doc = load_presentation(PRESENTATION / "structure.json")
    editorial = load_presentation(PRESENTATION / "editorial" / f"{name}.json")
    require(editorial.get("package") == name, f"{name}: editorial package mismatch")
    forbidden = sorted(FORBIDDEN_EDITORIAL_KEYS.intersection(editorial))
    require(not forbidden, f"{name}: editorial duplicates authoritative data: {', '.join(forbidden)}")
    entry = next((x for x in structure_doc.get("packages", []) if x.get("name") == name), None)
    require(isinstance(entry, dict), f"{name}: missing presentation structure")
    require(entry.get("sections") == ["package", "installation", "contents"],
            f"{name}: unsupported section composition")
    document = entry.get("document")
    require(isinstance(document, dict), f"{name}: missing presentation document identity")
    for field in ("section_id", "filename", "contents_id"):
        require(isinstance(document.get(field), str) and document[field],
                f"{name}: missing presentation document {field}")
    return resolve([name])["packages"][0], entry, editorial

def add_text(parent: ET.Element, tag: str, value: str, **attrs: str) -> ET.Element:
    node = ET.SubElement(parent, tag, attrs)
    node.text = value
    return node

def append_inline_text(parent: ET.Element, value: str) -> None:
    require(isinstance(value, str), "inline text must be a string")
    if len(parent):
        parent[-1].tail = (parent[-1].tail or "") + value
    else:
        parent.text = (parent.text or "") + value

def render_inline(parent: ET.Element, content: Any) -> None:
    require(isinstance(content, list), "rich inline content must be a list")
    for part in content:
        require(isinstance(part, dict), "inline content part must be an object")
        kind = part.get("type")
        text = part.get("text")
        require(isinstance(text, str), "inline content part requires text")
        if kind == "text":
            append_inline_text(parent, text)
            continue
        tag = INLINE_TAGS.get(kind)
        require(tag is not None, f"unsupported inline content type: {kind}")
        node = ET.SubElement(parent, tag)
        node.text = text

def add_rich_text(
    parent: ET.Element,
    tag: str,
    source: dict[str, Any],
    *,
    role: str | None = None,
) -> ET.Element:
    attrs = {"role": role} if role else {}
    node = ET.SubElement(parent, tag, attrs)
    has_text = "text" in source
    has_content = "content" in source
    require(has_text != has_content, f"{tag}: exactly one of text/content is required")
    if has_text:
        require(isinstance(source["text"], str), f"{tag}: text must be a string")
        node.text = source["text"]
    else:
        render_inline(node, source["content"])
    return node

def command_index(package: dict[str, Any]) -> tuple[dict[str, tuple[dict[str, Any], dict[str, Any]]], list[str]]:
    by_id: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    order: list[str] = []
    for step in package["procedure"]:
        for command in step["commands"]:
            command_id = command.get("id")
            require(isinstance(command_id, str) and command_id,
                    f"{package['name']}: presentation command missing stable id")
            require(command_id not in by_id, f"{package['name']}: duplicate command id {command_id}")
            by_id[command_id] = (step, command)
            order.append(command_id)
    return by_id, order

def command_remap(phase: str) -> str:
    return {"prepare": "pre", "build": "make"}.get(phase, phase)

def render_metrics(parent: ET.Element, package: dict[str, Any]) -> None:
    metrics = package.get("reference_metrics")
    require(isinstance(metrics, dict), f"{package['name']}: missing reference metrics")
    segmented = ET.SubElement(parent, "segmentedlist", {"role": "reference-metrics"})
    add_text(segmented, "segtitle", "Approximate build time")
    add_text(segmented, "segtitle", "Required disk space")
    item = ET.SubElement(segmented, "seglistitem")
    for field, role in (("build_time", "build-time"), ("disk_space", "disk-space")):
        value = metrics.get(field)
        require(isinstance(value, str) and value, f"{package['name']}: missing {field}")
        add_text(item, "seg", value, role=role)

def render_definition_list(parent: ET.Element, block: dict[str, Any]) -> None:
    variable = ET.SubElement(parent, "variablelist", {"role": "editorial-definition-list"})
    add_text(variable, "title", block["title"])
    items = block.get("items")
    require(isinstance(items, list) and items, "definition-list requires items")
    for item in items:
        require(isinstance(item.get("term"), str), "definition-list item requires term")
        entry = ET.SubElement(variable, "varlistentry")
        term = ET.SubElement(entry, "term")
        add_text(term, "parameter", item["term"])
        listitem = ET.SubElement(entry, "listitem")
        add_rich_text(listitem, "para", item, role="editorial-definition")

def render_installation(root: ET.Element, package: dict[str, Any], editorial: dict[str, Any]) -> None:
    install = ET.SubElement(root, "sect2", {"role": "installation"})
    add_text(install, "title", editorial["installation_title"])
    commands, authoritative_order = command_index(package)
    blocks = editorial.get("installation_blocks")
    require(isinstance(blocks, list) and blocks, f"{package['name']}: missing installation blocks")
    rendered_commands: list[str] = []

    for block in blocks:
        kind = block.get("type")
        if kind == "paragraph":
            add_rich_text(install, "para", block, role="editorial-paragraph")
        elif kind == "command":
            command_id = block.get("command_id")
            require(command_id in commands, f"{package['name']}: unknown command reference {command_id}")
            require(command_id not in rendered_commands, f"{package['name']}: duplicate command reference {command_id}")
            step, command = commands[command_id]
            rendered_commands.append(command_id)
            screen = ET.SubElement(install, "screen", {"format": "linespecific"})
            add_text(screen, "userinput", command["command"], role="build-command",
                     command_id=command_id, remap=command_remap(step["phase"]),
                     condition=step["condition"], user=command["user"])
        elif kind == "admonition":
            tag = block.get("kind")
            require(tag in ("important", "note", "warning", "caution"), f"{package['name']}: invalid admonition")
            node = ET.SubElement(install, tag, {"role": "editorial-admonition"})
            if block.get("title"):
                add_text(node, "title", block["title"])
            paragraphs = block.get("paragraphs")
            require(isinstance(paragraphs, list) and paragraphs, f"{package['name']}: empty admonition")
            for paragraph in paragraphs:
                if isinstance(paragraph, str):
                    add_text(node, "para", paragraph, role="admonition-text")
                else:
                    require(isinstance(paragraph, dict), f"{package['name']}: invalid admonition paragraph")
                    add_rich_text(node, "para", paragraph, role="admonition-text")
        elif kind == "definition-list":
            render_definition_list(install, block)
        else:
            raise RuntimeError(f"{package['name']}: unsupported editorial block {kind}")

    require(rendered_commands == authoritative_order,
            f"{package['name']}: editorial command order/coverage drift")

def category_label(key: str, count: int) -> str:
    if key == "programs": return "Installed program" if count == 1 else "Installed programs"
    if key == "libraries": return "Installed library" if count == 1 else "Installed libraries"
    if key == "directories": return "Installed directory" if count == 1 else "Installed directories"
    raise RuntimeError(f"unsupported installed category: {key}")

def render_installed_summary(parent: ET.Element, package: dict[str, Any]) -> None:
    installed = package.get("installed")
    require(isinstance(installed, dict), f"{package['name']}: missing installed summary")
    present = [(k, v) for k, v in installed.items() if v]
    require(present, f"{package['name']}: empty installed summary")
    segmented = ET.SubElement(parent, "segmentedlist", {"role": "installed-summary"})
    for key, values in present:
        require(isinstance(values, list) and all(isinstance(x, str) and x for x in values),
                f"{package['name']}: invalid installed {key}")
        add_text(segmented, "segtitle", category_label(key, len(values)))
    item = ET.SubElement(segmented, "seglistitem")
    for key, values in present:
        add_text(item, "seg", ", ".join(values), role=f"installed-{key}")

def render_installed_term(parent: ET.Element, item: dict[str, Any]) -> None:
    kind = item.get("kind")
    require(kind in ("program", "library", "file", "directory"),
            f"invalid installed kind for {item.get('id')}")
    if kind == "program":
        add_text(parent, "command", item["name"], role="installed-name")
    else:
        attrs = {"role": "installed-name"}
        if kind == "library":
            attrs["class"] = "libraryfile"
        add_text(parent, "filename", item["name"], **attrs)

def render_contents(root: ET.Element, package: dict[str, Any], structure: dict[str, Any], editorial: dict[str, Any]) -> None:
    contents = ET.SubElement(root, "sect2", {XML_ID: structure["document"]["contents_id"], "role": "content"})
    add_text(contents, "title", editorial["contents_title"])
    render_installed_summary(contents, package)
    variable = ET.SubElement(contents, "variablelist")
    add_text(variable, "bridgehead", "Short Descriptions", renderas="sect3")
    for item in package["installed_descriptions"]:
        entry = ET.SubElement(variable, "varlistentry", {XML_ID: item["id"]})
        term = ET.SubElement(entry, "term")
        render_installed_term(term, item)
        listitem = ET.SubElement(entry, "listitem")
        add_text(listitem, "para", item["description"], role="installed-description")

def render_package(name: str) -> str:
    package, structure, editorial = package_inputs(name)
    root = ET.Element("sect1", {XML_ID: structure["document"]["section_id"], "role": "wrap"})
    add_text(root, "title", f"{structure['title']}-{package['version']}")
    summary = ET.SubElement(root, "sect2", {"role": "package"})
    ET.SubElement(summary, "title")
    add_text(summary, "para", package["description"], role="package-description")
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

def self_test_package(name: str) -> None:
    package, structure, _ = package_inputs(name)
    root = ET.fromstring(render_package(name))
    roles = collect_roles(root)
    require(root.tag == "sect1" and root.attrib.get("role") == "wrap", f"{name}: root hierarchy drift")
    require(root.attrib.get(XML_ID) == structure["document"]["section_id"], f"{name}: section identity drift")
    require([x.attrib.get("role") for x in root.findall("sect2")] == ["package","installation","content"],
            f"{name}: visible section hierarchy drift")
    metrics = package["reference_metrics"]
    require(roles.get("build-time") == [metrics["build_time"]], f"{name}: build-time drift")
    require(roles.get("disk-space") == [metrics["disk_space"]], f"{name}: disk-space drift")
    expected_commands = [c["command"] for s in package["procedure"] for c in s["commands"]]
    require(roles.get("build-command") == expected_commands, f"{name}: command drift")
    expected_names = [i["name"] for i in package["installed_descriptions"]]
    require(roles.get("installed-name") == expected_names, f"{name}: installed name drift")
    require(roles.get("installed-description") == [i["description"] for i in package["installed_descriptions"]],
            f"{name}: installed description drift")

def self_test() -> None:
    for name in PROOF_PACKAGES:
        self_test_package(name)
    binutils_root = ET.fromstring(render_package("binutils"))
    require(binutils_root.find(".//important") is not None, "binutils: missing important admonition")
    require(len(binutils_root.findall(".//variablelist[@role='editorial-definition-list']")) == 2,
            "binutils: missing parameter explanation lists")
    filenames = [node.text for node in binutils_root.findall(".//filename")]
    require("/usr/lib" in filenames and "/usr/lib64" in filenames,
            "binutils: missing inline filename semantics")
    literals = [node.text for node in binutils_root.findall(".//literal")]
    require("$(exec_prefix)/$(target_alias)" in literals,
            "binutils: missing inline literal semantics")

def main() -> int:
    parser = argparse.ArgumentParser(description="compile normalized LFS presentation proof")
    parser.add_argument("--package", default="zlib")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            print(json.dumps({"status":"success","milestone":"presentation-slice",
                              "packages":list(PROOF_PACKAGES),
                              "equivalence":"visible-semantic-structure"}, indent=2))
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
