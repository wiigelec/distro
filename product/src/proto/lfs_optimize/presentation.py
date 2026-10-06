#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import posixpath
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from resolve import HERE, load_json, resolve

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
    "application": "application",
    "systemitem": "systemitem",
    "envar": "envar",
    "option": "option",
    "computeroutput": "computeroutput",
    "replaceable": "replaceable",
    "function": "function",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_presentation(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(value.get("schema_version") == 1, f"unsupported presentation schema: {path}")
    return value


def structure_document() -> dict[str, Any]:
    return load_presentation(PRESENTATION / "structure.json")


def chapter_structure(name: str) -> dict[str, Any]:
    structure = structure_document()
    entry = next(
        (item for item in structure.get("chapters", []) if item.get("name") == name),
        None,
    )
    require(isinstance(entry, dict), f"{name}: missing chapter presentation structure")
    return entry


def package_document(name: str) -> dict[str, Any]:
    chapter = chapter_structure("chapter08")
    documents = chapter.get("package_documents")
    require(isinstance(documents, dict), "chapter08: package_documents must be an object")
    document = documents.get(name)
    require(isinstance(document, dict), f"{name}: missing package document identity")
    for field in ("section_id", "filename", "contents_id"):
        require(
            isinstance(document.get(field), str) and document[field],
            f"{name}: missing presentation document {field}",
        )
    return document


def package_inputs(name: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    structure = structure_document()
    editorial = load_presentation(PRESENTATION / "editorial" / f"{name}.json")
    require(editorial.get("package") == name, f"{name}: editorial package mismatch")
    forbidden = sorted(FORBIDDEN_EDITORIAL_KEYS.intersection(editorial))
    require(not forbidden, f"{name}: editorial duplicates authoritative data: {', '.join(forbidden)}")
    entry = next((x for x in structure.get("packages", []) if x.get("name") == name), None)
    document = package_document(name)
    if entry is None:
        entry = {
            "name": name,
            "title": document["title"],
            "sections": ["package", "installation", "contents"],
        }
    require(isinstance(entry, dict), f"{name}: invalid package presentation structure")
    require(
        "document" not in entry,
        f"{name}: package composition must not own document identity",
    )
    require(
        entry.get("sections") == ["package", "installation", "contents"],
        f"{name}: unsupported section composition",
    )
    entry = dict(entry)
    entry["document"] = document
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
        if kind == "link":
            href = part.get("href")
            label = part.get("label")
            require(
                isinstance(href, str) and href
                and isinstance(label, str) and label,
                "link requires href and label",
            )
            node = ET.SubElement(parent, "ulink", {"url": href})
            node.text = label
            continue
        if kind == "xref":
            target = part.get("target")
            label = part.get("label")
            require(
                isinstance(target, str) and target
                and isinstance(label, str) and label,
                "xref requires target and label",
            )
            attrs = {"linkend": target, "label": label}
            if isinstance(part.get("suffix"), str):
                attrs["suffix"] = part["suffix"]
            node = ET.SubElement(parent, "xref", attrs)
            node.text = label
            continue
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


def command_sequence(
    package: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (step, command)
        for step in package["procedure"]
        for command in step["commands"]
    ]


def command_index(package: dict[str, Any]) -> tuple[dict[str, tuple[dict[str, Any], dict[str, Any]]], list[str]]:
    by_id: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    order: list[str] = []
    for step in package["procedure"]:
        for command in step["commands"]:
            command_id = command.get("id")
            require(
                isinstance(command_id, str) and command_id,
                f"{package['name']}: presentation command missing stable id",
            )
            require(
                command_id not in by_id,
                f"{package['name']}: duplicate command id {command_id}",
            )
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
    if block.get("title"):
        add_text(variable, "title", block["title"])
    items = block.get("items")
    require(isinstance(items, list) and items, "definition-list requires items")
    for item in items:
        entry = ET.SubElement(variable, "varlistentry")
        term = ET.SubElement(entry, "term")
        if isinstance(item.get("term"), str):
            add_text(term, "parameter", item["term"])
        else:
            render_inline(term, item.get("term_content"))
        listitem = ET.SubElement(entry, "listitem")
        if "blocks" in item:
            for child in item["blocks"]:
                require(child.get("type") == "paragraph", "unsupported definition-list block")
                add_rich_text(listitem, "para", child, role="editorial-definition")
        else:
            add_rich_text(listitem, "para", item, role="editorial-definition")



def render_installation(
    root: ET.Element,
    package: dict[str, Any],
    editorial: dict[str, Any],
) -> None:
    install = ET.SubElement(root, "sect2", {"role": "installation"})
    add_text(install, "title", editorial["installation_title"])
    sequence = command_sequence(package)
    commands_by_id: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for step, command in sequence:
        command_id = command.get("id")
        if isinstance(command_id, str) and command_id:
            require(command_id not in commands_by_id, f"{package['name']}: duplicate command id {command_id}")
            commands_by_id[command_id] = (step, command)

    blocks = editorial.get("installation_blocks")
    require(isinstance(blocks, list) and blocks, f"{package['name']}: missing installation blocks")
    rendered_positions: list[int] = []

    for block in blocks:
        kind = block.get("type")
        if kind == "paragraph":
            add_rich_text(install, "para", block, role="editorial-paragraph")
        elif kind == "command":
            if "command_index" in block:
                position = block["command_index"]
                require(isinstance(position, int) and 0 <= position < len(sequence), f"{package['name']}: invalid command index {position}")
                step, command = sequence[position]
            else:
                command_id = block.get("command_id")
                require(command_id in commands_by_id, f"{package['name']}: unknown command reference {command_id}")
                step, command = commands_by_id[command_id]
                position = sequence.index((step, command))
            require(position not in rendered_positions, f"{package['name']}: duplicate command position {position}")
            rendered_positions.append(position)
            attrs = {
                "role": "build-command",
                "command_index": str(position),
                "remap": command_remap(step["phase"]),
                "condition": step["condition"],
                "user": command["user"],
            }
            if isinstance(command.get("id"), str):
                attrs["command_id"] = command["id"]
            screen = ET.SubElement(install, "screen", {"format": "linespecific"})
            add_text(screen, "userinput", command["command"], **attrs)
        elif kind == "pre":
            screen = ET.SubElement(install, "screen", {"format": "linespecific", "role": "editorial-output"})
            add_text(screen, "computeroutput", block["text"])
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
                    add_rich_text(node, "para", paragraph, role="admonition-text")
        elif kind == "definition-list":
            render_definition_list(install, block)
        else:
            raise RuntimeError(f"{package['name']}: unsupported editorial block {kind}")

    require(rendered_positions == list(range(len(sequence))), f"{package['name']}: editorial command order/coverage drift")



def render_installed_summary(
    parent: ET.Element,
    package: dict[str, Any],
    editorial: dict[str, Any],
) -> None:
    installed = package.get("installed")
    require(isinstance(installed, dict), f"{package['name']}: missing installed summary")
    present = [(key, values) for key, values in installed.items() if values]
    require(present, f"{package['name']}: empty installed summary")
    labels = editorial.get("installed_labels")
    require(isinstance(labels, dict), f"{package['name']}: missing installed labels")
    require(set(labels) == {key for key, _values in present}, f"{package['name']}: installed label/category drift")
    segmented = ET.SubElement(parent, "segmentedlist", {"role": "installed-summary"})
    for key, values in present:
        add_text(segmented, "segtitle", labels[key])
    item = ET.SubElement(segmented, "seglistitem")
    for key, values in present:
        if len(values) == 1:
            rendered_values = values[0]
        elif len(values) == 2:
            rendered_values = " and ".join(values)
        else:
            rendered_values = ", ".join(values[:-1]) + ", and " + values[-1]
        add_text(item, "seg", rendered_values, role=f"installed-{key}")



def render_installed_term(
    parent: ET.Element,
    item: dict[str, Any],
    kind: str,
) -> None:
    require(
        kind in ("program", "library", "file", "directory"),
        f"invalid installed term kind for {item.get('id')}",
    )
    if kind == "program":
        add_text(parent, "command", item["name"], role="installed-name")
    else:
        attrs = {"role": "installed-name"}
        if kind == "library":
            attrs["class"] = "libraryfile"
        add_text(parent, "filename", item["name"], **attrs)


def render_contents(
    root: ET.Element,
    package: dict[str, Any],
    structure: dict[str, Any],
    editorial: dict[str, Any],
) -> None:
    contents = ET.SubElement(
        root,
        "sect2",
        {
            XML_ID: structure["document"]["contents_id"],
            "role": "content",
        },
    )
    add_text(contents, "title", editorial["contents_title"])
    render_installed_summary(contents, package, editorial)
    variable = ET.SubElement(contents, "variablelist")
    add_text(variable, "bridgehead", "Short Descriptions", renderas="sect3")
    term_kinds = editorial.get("installed_term_kinds")
    require(
        isinstance(term_kinds, dict)
        and set(term_kinds) == {
            item["id"] for item in package["installed_descriptions"]
        },
        f"{package['name']}: installed term-kind coverage drift",
    )
    for item in package["installed_descriptions"]:
        entry = ET.SubElement(variable, "varlistentry", {XML_ID: item["id"]})
        term = ET.SubElement(entry, "term")
        render_installed_term(term, item, term_kinds[item["id"]])
        listitem = ET.SubElement(entry, "listitem")
        add_text(listitem, "para", item["description"], role="installed-description")


def render_package(name: str) -> str:
    package, structure, editorial = package_inputs(name)
    root = ET.Element(
        "sect1",
        {
            XML_ID: structure["document"]["section_id"],
            "role": "wrap",
        },
    )
    add_text(root, "title", f"{structure['title']}-{package['version']}")
    summary = ET.SubElement(root, "sect2", {"role": "package"})
    ET.SubElement(summary, "title")
    add_text(summary, "para", package["description"], role="package-description")
    render_metrics(summary, package)
    render_installation(root, package, editorial)
    render_contents(root, package, structure, editorial)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def compose_chapter(name: str) -> dict[str, Any]:
    chapter = chapter_structure(name)
    chapter_number = chapter.get("number")
    require(
        chapter_number is None or isinstance(chapter_number, (int, str)),
        f"{name}: invalid chapter number",
    )
    document = chapter.get("document")
    require(isinstance(document, dict), f"{name}: missing chapter document")
    for field in ("section_id", "filename", "title"):
        require(
            isinstance(document.get(field), str) and document[field],
            f"{name}: missing chapter document {field}",
        )

    pages: list[dict[str, Any]] = []
    if "package_documents" in chapter:
        require(name == "chapter08", f"{name}: unexpected package-composed chapter")
        package_set = load_json(HERE / "package-set.json")
        packages = package_set.get("packages")
        require(
            isinstance(packages, list) and packages,
            "package set must be a non-empty list",
        )

        package_documents = chapter.get("package_documents")
        require(
            isinstance(package_documents, dict),
            f"{name}: package_documents must be an object",
        )
        require(
            set(package_documents) == set(packages),
            f"{name}: package document identities do not match authoritative package set",
        )

        for page in chapter.get("leading_pages", []):
            page_copy = dict(page)
            page_copy["kind"] = "editorial"
            pages.append(page_copy)

        for package_name in packages:
            document_entry = dict(package_documents[package_name])
            document_entry["kind"] = "package"
            document_entry["package"] = package_name
            pages.append(document_entry)

        for page in chapter.get("trailing_pages", []):
            page_copy = dict(page)
            page_copy["kind"] = "editorial"
            pages.append(page_copy)
    else:
        source_pages = chapter.get("pages")
        require(isinstance(source_pages, list), f"{name}: pages must be a list")
        for page in source_pages:
            require(isinstance(page, dict), f"{name}: page must be an object")
            page_copy = dict(page)
            page_copy["kind"] = "editorial"
            pages.append(page_copy)

    for index, page in enumerate(pages, start=1):
        require(
            isinstance(page.get("section_id"), str) and page["section_id"],
            f"{name}: page {index} missing section_id",
        )
        require(
            isinstance(page.get("filename"), str) and page["filename"],
            f"{name}: page {index} missing filename",
        )
        page["number"] = (
            f"{chapter_number}.{index}" if chapter_number is not None else None
        )
        page["previous"] = pages[index - 2]["section_id"] if index > 1 else None
        page["next"] = pages[index]["section_id"] if index < len(pages) else None

    return {
        "name": name,
        "kind": chapter.get("kind"),
        "number": chapter_number,
        "document": dict(document),
        "pages": pages,
    }


def _book_document(
    document: dict[str, Any],
    *,
    kind: str,
    owner: str,
    number: str | int | None = None,
    directory: str = "",
    up: str | None = None,
) -> dict[str, Any]:
    result = dict(document)
    require(
        isinstance(result.get("section_id"), str) and result["section_id"],
        f"{owner}: missing document section_id",
    )
    require(
        isinstance(result.get("filename"), str) and result["filename"],
        f"{owner}: missing document filename",
    )
    require(isinstance(directory, str), f"{owner}: invalid document directory")
    result["kind"] = kind
    result["owner"] = owner
    result["number"] = str(number) if number is not None else None
    result["directory"] = directory
    result["output_path"] = (
        posixpath.join(directory, result["filename"])
        if directory
        else result["filename"]
    )
    result["up"] = up
    return result


def compose_book() -> dict[str, Any]:
    structure = structure_document()
    book = structure.get("book")
    require(isinstance(book, dict), "missing book presentation structure")
    require(
        isinstance(book.get("title"), str) and book["title"],
        "book: missing title",
    )

    chapters = {
        entry.get("name"): entry
        for entry in structure.get("chapters", [])
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    require(
        len(chapters) == len(structure.get("chapters", [])),
        "book: invalid or duplicate chapter names",
    )

    documents: list[dict[str, Any]] = []

    def append_unit(name: str, up: str | None) -> None:
        require(name in chapters, f"book: unknown unit {name}")
        compiled = compose_chapter(name)
        unit_document = compiled["document"]
        directory = unit_document.get("directory", "")
        require(isinstance(directory, str), f"{name}: invalid document directory")
        unit_id = unit_document["section_id"]
        documents.append(
            _book_document(
                unit_document,
                kind=compiled["kind"] or "chapter",
                owner=name,
                number=compiled["number"],
                directory=directory,
                up=up,
            )
        )
        for page in compiled["pages"]:
            page_doc = _book_document(
                page,
                kind=page["kind"],
                owner=name,
                number=page["number"],
                directory=directory,
                up=unit_id,
            )
            if page.get("package"):
                page_doc["package"] = page["package"]
            documents.append(page_doc)

    frontmatter = book.get("frontmatter")
    require(isinstance(frontmatter, list), "book: frontmatter must be a list")
    for name in frontmatter:
        require(isinstance(name, str) and name, "book: invalid frontmatter entry")
        append_unit(name, None)

    parts = book.get("parts")
    require(isinstance(parts, list) and parts, "book: parts must be a non-empty list")
    seen_parts: set[str] = set()
    seen_units = set(frontmatter)
    for part_index, part in enumerate(parts, start=1):
        require(isinstance(part, dict), "book: part must be an object")
        part_name = part.get("name")
        require(
            isinstance(part_name, str)
            and part_name
            and part_name not in seen_parts,
            "book: invalid or duplicate part name",
        )
        seen_parts.add(part_name)

        part_document = part.get("document")
        require(isinstance(part_document, dict), f"{part_name}: missing document")
        part_id = part_document["section_id"]
        part_number = part.get("number")
        require(
            isinstance(part_number, str) and part_number,
            f"{part_name}: missing part number",
        )
        documents.append(
            _book_document(
                part_document,
                kind="part",
                owner=part_name,
                number=part_number,
                directory=part_document.get("directory", ""),
                up=None,
            )
        )

        children = part.get("children")
        require(isinstance(children, list), f"{part_name}: children must be a list")
        for name in children:
            require(
                isinstance(name, str)
                and name
                and name not in seen_units,
                f"{part_name}: invalid or duplicate child {name}",
            )
            seen_units.add(name)
            append_unit(name, part_id)

    require(
        seen_units == set(chapters),
        "book: chapter units do not match composed frontmatter/parts",
    )

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, document in enumerate(documents):
        section_id = document["section_id"]
        output_path = document["output_path"]
        require(section_id not in seen_ids, f"book: duplicate document id {section_id}")
        require(
            output_path not in seen_paths,
            f"book: duplicate chunk output path {output_path}",
        )
        seen_ids.add(section_id)
        seen_paths.add(output_path)
        document["previous"] = documents[index - 1]["section_id"] if index else None
        document["next"] = (
            documents[index + 1]["section_id"]
            if index + 1 < len(documents)
            else None
        )

    return {"title": book["title"], "documents": documents}

def book_target_index() -> dict[str, dict[str, Any]]:
    compiled = compose_book()
    index = {
        document["section_id"]: {
            **document,
            "target_id": document["section_id"],
            "nested": False,
            "document_id": document["section_id"],
        }
        for document in compiled["documents"]
    }

    structure = structure_document()
    book = structure.get("book")
    require(isinstance(book, dict), "missing book presentation structure")
    nested_targets = book.get("nested_targets")
    require(
        isinstance(nested_targets, list),
        "book: nested_targets must be a list",
    )

    for item in nested_targets:
        require(
            isinstance(item, dict),
            "book: nested target must be an object",
        )
        target_id = item.get("target_id")
        kind = item.get("kind")
        document_id = item.get("document_id")
        require(
            isinstance(target_id, str)
            and target_id
            and isinstance(kind, str)
            and kind
            and isinstance(document_id, str)
            and document_id,
            "book: invalid nested target",
        )
        require(
            target_id not in index,
            f"book: duplicate xref target {target_id}",
        )
        require(
            document_id in index and not index[document_id]["nested"],
            f"book: nested target {target_id} has unknown document {document_id}",
        )
        document = index[document_id]
        index[target_id] = {
            "target_id": target_id,
            "section_id": target_id,
            "kind": kind,
            "nested": True,
            "document_id": document_id,
            "filename": document["filename"],
            "owner": document["owner"],
            "number": document.get("number"),
        }

    return index


def resolve_book_xref(target: str) -> dict[str, Any]:
    require(
        isinstance(target, str) and target,
        "xref target must be non-empty",
    )
    index = book_target_index()
    require(
        target in index,
        f"unresolved book-graph xref: {target}",
    )
    return dict(index[target])


def render_chapter_hierarchy(name: str) -> str:
    compiled = compose_chapter(name)
    document = compiled["document"]
    attrs = {
        XML_ID: document["section_id"],
        "filename": document["filename"],
        "kind": compiled["kind"] or "chapter",
    }
    if compiled["number"] is not None:
        attrs["number"] = str(compiled["number"])
    root = ET.Element("chapter-map", attrs)
    add_text(root, "title", document["title"])
    for page in compiled["pages"]:
        page_attrs = {
            XML_ID: page["section_id"],
            "filename": page["filename"],
            "kind": page["kind"],
        }
        if page.get("number") is not None:
            page_attrs["number"] = page["number"]
        if page.get("package"):
            page_attrs["package"] = page["package"]
        if page.get("previous"):
            page_attrs["previous"] = page["previous"]
        if page.get("next"):
            page_attrs["next"] = page["next"]
        ET.SubElement(root, "page", page_attrs)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def render_book_hierarchy() -> str:
    compiled = compose_book()
    root = ET.Element("book-map")
    add_text(root, "title", compiled["title"])
    for document in compiled["documents"]:
        attrs = {
            XML_ID: document["section_id"],
            "filename": document["filename"],
            "kind": document["kind"],
            "owner": document["owner"],
        }
        if document.get("number") is not None:
            attrs["number"] = document["number"]
        if document.get("package"):
            attrs["package"] = document["package"]
        if document.get("previous"):
            attrs["previous"] = document["previous"]
        if document.get("next"):
            attrs["next"] = document["next"]
        ET.SubElement(root, "document", attrs)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def book_document_index() -> dict[str, dict[str, Any]]:
    return {
        document["section_id"]: document
        for document in compose_book()["documents"]
    }


def relative_chunk_href(source_path: str, target_path: str) -> str:
    source_directory = posixpath.dirname(source_path) or "."
    return posixpath.relpath(target_path, source_directory)


def document_nav(document: dict[str, Any]) -> dict[str, str]:
    index = book_document_index()
    source_path = document["output_path"]
    nav = {
        "home": relative_chunk_href(source_path, "index.html"),
    }
    for relation in ("previous", "next", "up"):
        target_id = document.get(relation)
        if target_id:
            require(target_id in index, f"{document['section_id']}: unknown {relation} target")
            nav[relation] = relative_chunk_href(
                source_path,
                index[target_id]["output_path"],
            )
    return nav


def resolve_chunked_xref(source_document_id: str, target: str) -> str:
    index = book_document_index()
    require(source_document_id in index, f"unknown source document: {source_document_id}")
    resolved = resolve_book_xref(target)
    target_document_id = resolved["document_id"]
    require(target_document_id in index, f"xref target document missing: {target_document_id}")
    source_path = index[source_document_id]["output_path"]
    target_path = index[target_document_id]["output_path"]
    href = relative_chunk_href(source_path, target_path)
    if resolved["nested"]:
        href += "#" + target
    return href


def document_display_title(document: dict[str, Any]) -> str:
    title = document.get("title")
    if document.get("package"):
        package_name = document["package"]
        package = resolve([package_name])["packages"][0]
        title = document.get("title")
        require(isinstance(title, str) and title, f"{package_name}: missing presentation title")
        title = f"{title}-{package['version']}"
    require(isinstance(title, str) and title, f"{document['section_id']}: missing title")

    number = document.get("number")
    if document["kind"] == "part" and number:
        return f"Part {number}. {title}"
    if document["kind"] == "chapter" and number:
        return f"Chapter {number}. {title}"
    if document["kind"] == "appendix" and number:
        return f"Appendix {number}. {title}"
    if number:
        return f"{number}. {title}"
    return title


def document_h1(document: dict[str, Any]) -> str:
    title = document_display_title(document)
    if document.get("package") and document.get("number"):
        prefix = f"{document['number']}."
        if title.startswith(prefix):
            return document["number"] + title[len(prefix):]
    return title


def package_book_document(name: str) -> dict[str, Any]:
    documents = compose_book()["documents"]
    matches = [
        document
        for document in documents
        if document.get("package") == name
    ]
    require(
        len(matches) == 1,
        f"{name}: expected exactly one package document in book graph",
    )
    return matches[0]


def package_nav(name: str) -> dict[str, str]:
    return document_nav(package_book_document(name))

def _html_inline(
    parent: ET.Element,
    source: ET.Element,
    *,
    source_document_id: str | None = None,
) -> None:
    if source.text:
        parent.text = source.text
    for child in source:
        if child.tag in ("filename", "literal", "command", "parameter", "application", "systemitem", "envar", "option", "computeroutput", "function"):
            target = ET.SubElement(parent, "code")
        elif child.tag == "replaceable":
            target = ET.SubElement(parent, "var")
        elif child.tag == "quote":
            target = ET.SubElement(parent, "q")
        elif child.tag == "emphasis":
            target = ET.SubElement(parent, "em")
        elif child.tag == "ulink":
            target = ET.SubElement(parent, "a", {"href": child.attrib["url"]})
        elif child.tag == "xref":
            require(source_document_id is not None, "package xref requires source document identity")
            target = ET.SubElement(parent, "a", {
                "href": resolve_chunked_xref(source_document_id, child.attrib["linkend"]),
                "data-xref-target": child.attrib["linkend"],
            })
        else:
            target = ET.SubElement(parent, "span")
        target.text = child.text
        target.tail = child.tail
        if child.tag == "xref" and child.attrib.get("suffix"):
            target.tail = (target.tail or "") + child.attrib["suffix"]



def render_chunked_html_package(name: str) -> str:
    semantic = ET.fromstring(render_package(name))
    package, package_structure, editorial = package_inputs(name)
    document = package_book_document(name)
    nav = package_nav(name)
    number = document.get("number")
    require(
        isinstance(number, str) and number,
        f"{name}: missing package page number",
    )

    html = ET.Element("html")
    head = ET.SubElement(html, "head")
    add_text(head, "title", f"{number}. {package_structure['title']}-{package['version']}")
    body = ET.SubElement(
        html,
        "body",
        {
            "id": package_structure["document"]["section_id"],
            "data-filename": document["filename"],
            "data-output-path": document["output_path"],
        },
    )

    def add_nav(role: str) -> None:
        nav_node = ET.SubElement(body, "nav", {"data-role": role})
        for relation in ("previous", "next", "up", "home"):
            if relation in nav:
                add_text(
                    nav_node,
                    "a",
                    relation.capitalize(),
                    rel=relation,
                    href=nav[relation],
                )

    add_nav("top")
    add_text(
        body,
        "h1",
        f"{number} {package_structure['title']}-{package['version']}",
    )

    summary = semantic.find("sect2[@role='package']")
    require(summary is not None, f"{name}: semantic summary missing")
    description = summary.find("para[@role='package-description']")
    require(description is not None, f"{name}: package description missing")
    add_text(
        body,
        "p",
        description.text or "",
        **{"data-role": "package-description"},
    )

    metrics = summary.find("segmentedlist[@role='reference-metrics']")
    require(metrics is not None, f"{name}: reference metrics missing")
    metric_titles = [node.text or "" for node in metrics.findall("segtitle")]
    metric_values = [node.text or "" for node in metrics.findall("seglistitem/seg")]
    require(len(metric_titles) == len(metric_values) == 2, f"{name}: invalid metrics")
    metric_dl = ET.SubElement(body, "dl", {"data-role": "reference-metrics"})
    for title, value in zip(metric_titles, metric_values):
        add_text(metric_dl, "dt", title)
        add_text(metric_dl, "dd", value)

    install = semantic.find("sect2[@role='installation']")
    require(install is not None, f"{name}: semantic installation missing")
    add_text(body, "h2", f"{number}.1 {editorial['installation_title']}")

    for child in install:
        if child.tag == "title":
            continue
        if child.tag == "para":
            p = ET.SubElement(body, "p", {"data-role": child.attrib.get("role", "")})
            _html_inline(p, child, source_document_id=document["section_id"])
        elif child.tag == "screen":
            pre = ET.SubElement(body, "pre")
            command = child.find("userinput")
            output = child.find("computeroutput")
            require((command is None) != (output is None), f"{name}: invalid screen payload")
            if command is not None:
                attrs = {
                    "data-command-index": command.attrib["command_index"],
                    "data-phase": command.attrib["remap"],
                }
                if "command_id" in command.attrib:
                    attrs["data-command-id"] = command.attrib["command_id"]
                add_text(pre, "code", command.text or "", **attrs)
            else:
                add_text(pre, "samp", output.text or "", **{"data-role": "editorial-output"})
        elif child.tag == "variablelist":
            title = child.findtext("title")
            if title:
                add_text(body, "h3", title)
            dl = ET.SubElement(body, "dl", {"data-role": "editorial-definition-list"})
            for entry in child.findall("varlistentry"):
                term = entry.find("term")
                require(term is not None, f"{name}: definition term missing")
                dt = ET.SubElement(dl, "dt")
                _html_inline(dt, term, source_document_id=document["section_id"])
                paras = entry.findall("listitem/para")
                require(paras, f"{name}: definition text missing")
                dd = ET.SubElement(dl, "dd")
                for para in paras:
                    p = ET.SubElement(dd, "p")
                    _html_inline(p, para, source_document_id=document["section_id"])
        elif child.tag in ("important", "note", "warning", "caution"):
            aside = ET.SubElement(body, "aside", {"data-kind": child.tag})
            title = child.findtext("title")
            if title:
                add_text(aside, "h3", title)
            for para in child.findall("para"):
                p = ET.SubElement(aside, "p")
                _html_inline(p, para, source_document_id=document["section_id"])
        else:
            raise RuntimeError(f"{name}: unsupported HTML source node {child.tag}")

    contents = semantic.find("sect2[@role='content']")
    require(contents is not None, f"{name}: semantic contents missing")
    add_text(
        body,
        "h2",
        f"{number}.2 {editorial['contents_title']}",
        id=package_structure["document"]["contents_id"],
    )

    installed = contents.find("segmentedlist[@role='installed-summary']")
    require(installed is not None, f"{name}: installed summary missing")
    installed_titles = [node.text or "" for node in installed.findall("segtitle")]
    installed_values = [node.text or "" for node in installed.findall("seglistitem/seg")]
    require(
        len(installed_titles) == len(installed_values),
        f"{name}: installed summary arity drift",
    )
    installed_dl = ET.SubElement(body, "dl", {"data-role": "installed-summary"})
    for title, value in zip(installed_titles, installed_values):
        add_text(installed_dl, "dt", title)
        add_text(installed_dl, "dd", value)

    add_text(body, "h3", "Short Descriptions")
    descriptions = ET.SubElement(body, "dl", {"data-role": "short-descriptions"})
    for entry in contents.findall("variablelist/varlistentry"):
        item_id = entry.attrib.get(XML_ID)
        require(isinstance(item_id, str) and item_id, f"{name}: installed item id missing")
        dt = ET.SubElement(descriptions, "dt", {"id": item_id})
        term = entry.find("term")
        require(term is not None and len(term) == 1, f"{name}: installed term missing")
        _html_inline(dt, term)
        para = entry.find("listitem/para")
        require(para is not None, f"{name}: installed description missing")
        dd = ET.SubElement(descriptions, "dd")
        _html_inline(dd, para)

    add_nav("bottom")
    ET.indent(html, space="  ")
    return ET.tostring(html, encoding="unicode", method="html")


def editorial_document_path(section_id: str) -> Path:
    return PRESENTATION / "editorial-documents" / f"{section_id}.json"


def load_editorial_document(section_id: str) -> dict[str, Any] | None:
    path = editorial_document_path(section_id)
    if not path.is_file():
        return None
    document = load_presentation(path)
    require(
        document.get("document_id") == section_id,
        f"{section_id}: editorial document identity mismatch",
    )
    require(
        isinstance(document.get("blocks"), list),
        f"{section_id}: editorial blocks must be a list",
    )
    return document


def bootstrap_stage(section_id: str) -> dict[str, Any]:
    bootstrap = load_json(HERE / "bootstrap-13.1.json")
    matches = [
        stage for stage in bootstrap.get("stages", [])
        if stage.get("id") == section_id
    ]
    require(
        len(matches) == 1,
        f"{section_id}: bootstrap stage not found",
    )
    return matches[0]


def _render_editorial_inline(
    parent: ET.Element,
    content: list[dict[str, Any]],
    source_document_id: str,
) -> None:
    def append(value: str) -> None:
        if len(parent):
            parent[-1].tail = (parent[-1].tail or "") + value
        else:
            parent.text = (parent.text or "") + value

    for part in content:
        kind = part.get("type")
        if kind == "text":
            append(part["text"])
            continue
        if kind == "xref":
            node = ET.SubElement(
                parent,
                "a",
                {
                    "href": resolve_chunked_xref(
                        source_document_id,
                        part["target"],
                    ),
                    "data-xref-target": part["target"],
                },
            )
            node.text = part["label"]
            if part.get("suffix"):
                node.tail = part["suffix"]
            continue
        if kind == "link":
            node = ET.SubElement(parent, "a", {"href": part["href"]})
            node.text = part["label"]
            continue
        if kind == "emphasis":
            node = ET.SubElement(parent, "em")
            node.text = part["text"]
            continue
        if kind == "quote":
            node = ET.SubElement(parent, "q")
            node.text = part["text"]
            continue
        if kind == "replaceable":
            node = ET.SubElement(parent, "var")
            node.text = part["text"]
            continue
        if kind == "code":
            node = ET.SubElement(parent, "code")
            node.text = part["text"]
            continue
        if kind == "key":
            node = ET.SubElement(parent, "kbd")
            node.text = part["text"]
            continue
        if kind == "keycombo":
            node = ET.SubElement(parent, "kbd")
            node.text = "+".join(part["keys"])
            node.set("data-keycombo", "true")
            continue
        if kind == "superscript":
            node = ET.SubElement(parent, "sup")
            node.text = part["text"]
            continue
        if kind == "footnote":
            node = ET.SubElement(parent, "span", {"data-role": "footnote"})
            node.text = "["
            _render_editorial_inline(
                node,
                part["content"],
                source_document_id,
            )
            if len(node):
                node[-1].tail = (node[-1].tail or "") + "]"
            else:
                node.text = (node.text or "") + "]"
            continue
        raise RuntimeError(
            f"{source_document_id}: unsupported editorial inline {kind}"
        )


def _render_editorial_blocks(
    parent: ET.Element,
    blocks: list[dict[str, Any]],
    source_document_id: str,
    *,
    heading_level: int = 2,
) -> None:
    section_index = 0
    for block in blocks:
        kind = block.get("type")
        if kind == "paragraph":
            node = ET.SubElement(parent, "p")
            _render_editorial_inline(
                node,
                block["content"],
                source_document_id,
            )
        elif kind == "pre":
            node = ET.SubElement(parent, "pre")
            node.text = block["text"]
        elif kind == "bootstrap_command":
            stage = bootstrap_stage(source_document_id)
            index = block["index"]
            commands = stage.get("commands")
            require(
                isinstance(commands, list)
                and 0 <= index < len(commands),
                f"{source_document_id}: bootstrap command index out of range",
            )
            pre = ET.SubElement(parent, "pre")
            add_text(
                pre,
                "code",
                commands[index],
                **{"data-bootstrap-command": str(index)},
            )
        elif kind == "list":
            list_node = ET.SubElement(
                parent,
                "ol" if block.get("ordered") else "ul",
            )
            for item in block["items"]:
                li = ET.SubElement(list_node, "li")
                _render_editorial_blocks(
                    li,
                    item,
                    source_document_id,
                    heading_level=heading_level,
                )
        elif kind == "admonition":
            aside = ET.SubElement(
                parent,
                "aside",
                {"data-kind": block["kind"]},
            )
            if block.get("title"):
                add_text(aside, f"h{min(heading_level, 6)}", block["title"])
            _render_editorial_blocks(
                aside,
                block["blocks"],
                source_document_id,
                heading_level=min(heading_level + 1, 6),
            )
        elif kind == "section":
            section_index += 1
            attrs = {}
            if block.get("id"):
                attrs["id"] = block["id"]
            section = ET.SubElement(parent, "section", attrs)
            if block.get("title"):
                add_text(
                    section,
                    f"h{min(heading_level, 6)}",
                    block["title"],
                )
            _render_editorial_blocks(
                section,
                block["blocks"],
                source_document_id,
                heading_level=min(heading_level + 1, 6),
            )
        elif kind == "heading":
            add_text(
                parent,
                f"h{min(heading_level, 6)}",
                block["text"],
            )
        elif kind == "definition_list":
            if block.get("title"):
                add_text(
                    parent,
                    f"h{min(heading_level, 6)}",
                    block["title"],
                )
            dl = ET.SubElement(parent, "dl")
            for entry in block["entries"]:
                dt = ET.SubElement(dl, "dt")
                _render_editorial_inline(
                    dt,
                    entry["term"],
                    source_document_id,
                )
                dd = ET.SubElement(dl, "dd")
                _render_editorial_blocks(
                    dd,
                    entry["blocks"],
                    source_document_id,
                    heading_level=heading_level,
                )
        elif kind == "segmented_list":
            require(
                len(block["titles"]) == len(block["values"]),
                f"{source_document_id}: segmented-list arity mismatch",
            )
            dl = ET.SubElement(parent, "dl")
            for title, value in zip(block["titles"], block["values"]):
                add_text(dl, "dt", title)
                add_text(dl, "dd", value)
        elif kind == "flow":
            _render_editorial_blocks(
                parent,
                block["blocks"],
                source_document_id,
                heading_level=heading_level,
            )
        elif kind == "blockquote":
            quote = ET.SubElement(parent, "blockquote")
            _render_editorial_blocks(
                quote,
                block["blocks"],
                source_document_id,
                heading_level=heading_level,
            )
        elif kind == "table":
            if block.get("title"):
                add_text(
                    parent,
                    f"h{min(heading_level, 6)}",
                    block["title"],
                )
            table = ET.SubElement(parent, "table")
            if block.get("headers"):
                thead = ET.SubElement(table, "thead")
                row = ET.SubElement(thead, "tr")
                for value in block["headers"]:
                    add_text(row, "th", value)
            tbody = ET.SubElement(table, "tbody")
            for values in block["rows"]:
                row = ET.SubElement(tbody, "tr")
                for value in values:
                    add_text(row, "td", value)
        else:
            raise RuntimeError(
                f"{source_document_id}: unsupported editorial block {kind}"
            )


def render_chunked_html_editorial(
    document: dict[str, Any],
    editorial: dict[str, Any],
) -> str:
    section_id = document["section_id"]
    html = ET.Element("html")
    head = ET.SubElement(html, "head")
    add_text(head, "title", document_display_title(document))
    body = ET.SubElement(
        html,
        "body",
        {
            "id": section_id,
            "data-filename": document["filename"],
            "data-output-path": document["output_path"],
            "data-body-status": "complete",
        },
    )
    nav = document_nav(document)

    def add_nav(role: str) -> None:
        nav_node = ET.SubElement(body, "nav", {"data-role": role})
        for relation in ("previous", "next", "up", "home"):
            if relation in nav:
                add_text(
                    nav_node,
                    "a",
                    relation.capitalize(),
                    rel=relation,
                    href=nav[relation],
                )

    add_nav("top")
    add_text(body, "h1", document_h1(document))
    main = ET.SubElement(body, "main")
    _render_editorial_blocks(
        main,
        editorial["blocks"],
        section_id,
    )
    add_nav("bottom")
    ET.indent(html, space="  ")
    return ET.tostring(html, encoding="unicode", method="html")


def render_chunked_html_document(section_id: str) -> str:
    index = book_document_index()
    require(section_id in index, f"unknown book document: {section_id}")
    document = index[section_id]

    package_name = document.get("package")
    if package_name and (PRESENTATION / "editorial" / f"{package_name}.json").is_file():
        return render_chunked_html_package(package_name)

    editorial = load_editorial_document(section_id)
    if editorial is not None:
        return render_chunked_html_editorial(document, editorial)

    html = ET.Element("html")
    head = ET.SubElement(html, "head")
    display_title = document_display_title(document)
    add_text(head, "title", display_title)

    body = ET.SubElement(
        html,
        "body",
        {
            "id": section_id,
            "data-filename": document["filename"],
            "data-output-path": document["output_path"],
            "data-body-status": "pending-editorial-migration",
        },
    )
    nav = document_nav(document)

    def add_nav(role: str) -> None:
        nav_node = ET.SubElement(body, "nav", {"data-role": role})
        for relation in ("previous", "next", "up", "home"):
            if relation in nav:
                add_text(
                    nav_node,
                    "a",
                    relation.capitalize(),
                    rel=relation,
                    href=nav[relation],
                )

    add_nav("top")
    add_text(body, "h1", document_h1(document))
    add_nav("bottom")
    ET.indent(html, space="  ")
    return ET.tostring(html, encoding="unicode", method="html")


def render_chunked_html_book() -> dict[str, str]:
    rendered: dict[str, str] = {}
    for document in compose_book()["documents"]:
        output_path = document["output_path"]
        require(
            output_path not in rendered,
            f"duplicate rendered chunk path: {output_path}",
        )
        rendered[output_path] = render_chunked_html_document(
            document["section_id"]
        )
    return rendered


def chunked_html_snapshot(name: str) -> dict[str, Any]:
    root = ET.fromstring(render_chunked_html_package(name))
    body = root.find("body")
    require(body is not None, f"{name}: HTML body missing")

    nav = body.find("nav[@data-role='top']")
    require(nav is not None, f"{name}: top navigation missing")
    navigation = {
        link.attrib["rel"]: link.attrib["href"]
        for link in nav.findall("a")
    }

    metrics = body.find("dl[@data-role='reference-metrics']")
    installed = body.find("dl[@data-role='installed-summary']")
    require(metrics is not None and installed is not None, f"{name}: HTML summaries missing")

    return {
        "filename": body.attrib["data-filename"],
        "page_id": body.attrib["id"],
        "title": root.findtext("head/title"),
        "h1": body.findtext("h1"),
        "h2": [node.text or "" for node in body.findall("h2")],
        "navigation": navigation,
        "commands": [node.text or "" for node in body.findall("pre/code")],
        "metrics": {
            dt.text or "": dd.text or ""
            for dt, dd in zip(metrics.findall("dt"), metrics.findall("dd"))
        },
        "installed_summary": {
            dt.text or "": dd.text or ""
            for dt, dd in zip(installed.findall("dt"), installed.findall("dd"))
        },
    }


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
    require(
        root.tag == "sect1" and root.attrib.get("role") == "wrap",
        f"{name}: root hierarchy drift",
    )
    require(
        root.attrib.get(XML_ID) == structure["document"]["section_id"],
        f"{name}: section identity drift",
    )
    require(
        [item.attrib.get("role") for item in root.findall("sect2")]
        == ["package", "installation", "content"],
        f"{name}: visible section hierarchy drift",
    )
    metrics = package["reference_metrics"]
    require(roles.get("build-time") == [metrics["build_time"]], f"{name}: build-time drift")
    require(roles.get("disk-space") == [metrics["disk_space"]], f"{name}: disk-space drift")
    expected_commands = [
        command["command"]
        for step in package["procedure"]
        for command in step["commands"]
    ]
    require(roles.get("build-command") == expected_commands, f"{name}: command drift")
    expected_names = [item["name"] for item in package["installed_descriptions"]]
    require(roles.get("installed-name") == expected_names, f"{name}: installed name drift")
    require(
        roles.get("installed-description")
        == [item["description"] for item in package["installed_descriptions"]],
        f"{name}: installed description drift",
    )


def self_test_chapter08() -> None:
    compiled = compose_chapter("chapter08")
    pages = compiled["pages"]
    package_set = load_json(HERE / "package-set.json")["packages"]
    golden = load_presentation(PRESENTATION / "golden" / "chapter08-hierarchy.json")

    require(len(pages) == 85, "chapter08: expected 85 top-level pages")
    package_pages = [page for page in pages if page["kind"] == "package"]
    require(
        [page["package"] for page in package_pages] == package_set,
        "chapter08: package order does not come from authoritative package set",
    )

    generated_identity = [
        {
            "section_id": page["section_id"],
            "filename": page["filename"],
        }
        for page in pages
    ]
    require(
        generated_identity == golden["pages"],
        "chapter08: generated hierarchy drifted from LFS 13.1-systemd golden fixture",
    )
    require(
        {
            field: compiled["document"][field]
            for field in ("section_id", "filename", "title")
        }
        == golden["chapter"],
        "chapter08: chapter document identity drift",
    )

    expected_numbers = [f"8.{index}" for index in range(1, 86)]
    require(
        [page["number"] for page in pages] == expected_numbers,
        "chapter08: section numbering drift",
    )

    for index, page in enumerate(pages):
        expected_previous = pages[index - 1]["section_id"] if index else None
        expected_next = pages[index + 1]["section_id"] if index + 1 < len(pages) else None
        require(
            page["previous"] == expected_previous and page["next"] == expected_next,
            f"chapter08: local navigation drift at {page['section_id']}",
        )

    by_id = {page["section_id"]: page for page in pages}
    require(by_id["ch-system-zlib"]["number"] == "8.6", "chapter08: Zlib numbering drift")
    require(by_id["ch-system-binutils"]["number"] == "8.22", "chapter08: Binutils numbering drift")
    require(by_id["ch-system-e2fsprogs"]["number"] == "8.82", "chapter08: E2fsprogs numbering drift")
    require(by_id["ch-system-aboutdebug"]["number"] == "8.83", "chapter08: trailing-page numbering drift")

    parsed = ET.fromstring(render_chapter_hierarchy("chapter08"))
    require(
        parsed.attrib.get(XML_ID) == "chapter-building-system",
        "chapter08: rendered chapter identity drift",
    )
    require(
        len(parsed.findall("page")) == 85,
        "chapter08: rendered hierarchy page count drift",
    )


def self_test_nested_xrefs() -> None:
    golden = load_presentation(
        PRESENTATION / "golden" / "xref-targets.json"
    )
    require(
        golden.get("reference_count") == 161,
        "xref: source reference count drift",
    )
    require(
        golden.get("distinct_target_count") == 86,
        "xref: source target count drift",
    )

    targets = golden.get("targets")
    require(
        isinstance(targets, list) and len(targets) == 86,
        "xref: invalid golden target set",
    )
    expected_nested = {
        item["target_id"]: item
        for item in targets
        if item.get("nested")
    }
    require(
        len(expected_nested) == 38,
        "xref: expected 38 nested targets",
    )

    index = book_target_index()
    for item in targets:
        target_id = item["target_id"]
        resolved = resolve_book_xref(target_id)
        require(
            resolved["target_id"] == target_id,
            f"xref: target identity drift for {target_id}",
        )
        require(
            resolved["nested"] == item["nested"],
            f"xref: nesting classification drift for {target_id}",
        )
        require(
            resolved["document_id"] == item["document_id"],
            f"xref: document binding drift for {target_id}",
        )

    structure = structure_document()
    configured = structure["book"]["nested_targets"]
    require(
        {
            item["target_id"]: {
                "kind": item["kind"],
                "document_id": item["document_id"],
            }
            for item in configured
        }
        == {
            target_id: {
                "kind": item["kind"],
                "document_id": item["document_id"],
            }
            for target_id, item in expected_nested.items()
        },
        "xref: presentation nested target configuration drift",
    )

    contents = resolve_book_xref("contents-binutils")
    require(
        contents["nested"]
        and contents["filename"] == "binutils.html"
        and contents["document_id"] == "ch-system-binutils",
        "xref: package contents target drift",
    )
    bridgehead = resolve_book_xref("version-check")
    require(
        bridgehead["kind"] == "bridgehead"
        and bridgehead["filename"] == "hostreqs.html",
        "xref: bridgehead target drift",
    )
    anchor = resolve_book_xref("pie-ssp-info")
    require(
        anchor["kind"] == "anchor"
        and anchor["filename"] == "gcc.html",
        "xref: explicit anchor target drift",
    )
    license_target = resolve_book_xref("MIT")
    require(
        license_target["kind"] == "sect1"
        and license_target["document_id"] == "Licenses"
        and license_target["filename"] == "licenses.html",
        "xref: unchunked license section target drift",
    )


def self_test_book() -> None:
    compiled = compose_book()
    documents = compiled["documents"]
    golden = load_presentation(
        PRESENTATION / "golden" / "book-hierarchy.json"
    )

    generated_identity = [
        {
            "section_id": document["section_id"],
            "filename": document["filename"],
        }
        for document in documents
    ]
    require(
        generated_identity == golden["documents"],
        "book: generated document graph drifted from LFS 13.1-systemd golden fixture",
    )
    require(
        len(documents) == 199,
        "book: expected 199 chunked documents",
    )

    by_id = {
        document["section_id"]: document
        for document in documents
    }
    require(
        by_id["ch-tools-cleanup"]["next"] == "part4"
        and by_id["part4"]["previous"] == "ch-tools-cleanup"
        and by_id["part4"]["next"] == "chapter-building-system",
        "book: Chapter 7 -> Part IV navigation drift",
    )
    require(
        by_id["chapter-building-system"]["previous"] == "part4"
        and by_id["chapter-building-system"]["next"]
        == "ch-system-introduction",
        "book: Part IV -> Chapter 8 navigation drift",
    )
    require(
        by_id["ch-system-cleanup"]["next"] == "chapter-config",
        "book: Chapter 8 -> Chapter 9 navigation drift",
    )
    require(
        by_id["chapter-config"]["previous"] == "ch-system-cleanup"
        and by_id["chapter-config"]["next"] == "ch-config-introduction",
        "book: Chapter 9 boundary navigation drift",
    )

    require(
        resolve_book_xref("chapter-building-system")["filename"]
        == "chapter08.html",
        "book: chapter xref resolution drift",
    )
    zlib_target = resolve_book_xref("ch-system-zlib")
    require(
        zlib_target["filename"] == "zlib.html"
        and zlib_target["number"] == "8.6",
        "book: package-page xref resolution drift",
    )
    require(
        resolve_book_xref("appendixc")["filename"]
        == "dependencies.html",
        "book: appendix xref resolution drift",
    )

    try:
        resolve_book_xref("not-a-book-graph-target")
    except RuntimeError:
        pass
    else:
        raise RuntimeError("book: unresolved xref was accepted")

    parsed = ET.fromstring(render_book_hierarchy())
    require(
        len(parsed.findall("document")) == 199,
        "book: rendered document graph count drift",
    )


def self_test_chunked_html_book() -> None:
    golden = load_presentation(
        PRESENTATION / "golden" / "chunked-html-book.json"
    )
    documents = golden.get("documents")
    require(
        isinstance(documents, list)
        and len(documents) == golden.get("document_count") == 199,
        "chunked-html-book: invalid golden document set",
    )

    rendered = render_chunked_html_book()
    expected_paths = [item["output_path"] for item in documents]
    require(
        list(rendered) == expected_paths,
        "chunked-html-book: output path/order drift",
    )
    require(
        len(rendered) == len(set(rendered)) == 199,
        "chunked-html-book: output path collision",
    )

    for expected in documents:
        root = ET.fromstring(rendered[expected["output_path"]])
        body = root.find("body")
        require(body is not None, "chunked-html-book: missing body")
        require(
            body.attrib.get("id") == expected["section_id"]
            and body.attrib.get("data-output-path") == expected["output_path"],
            f"chunked-html-book: identity/route drift for {expected['section_id']}",
        )
        require(
            root.findtext("head/title") == expected["title"],
            f"chunked-html-book: head title drift for {expected['section_id']}",
        )
        require(
            isinstance(body.findtext("h1"), str) and body.findtext("h1"),
            f"chunked-html-book: missing document heading for {expected['section_id']}",
        )

        top = body.find("nav[@data-role='top']")
        bottom = body.find("nav[@data-role='bottom']")
        require(top is not None and bottom is not None, "chunked-html-book: nav missing")
        actual_nav = {
            node.attrib["rel"]: node.attrib["href"]
            for node in top.findall("a")
        }
        require(
            actual_nav == expected["navigation"],
            f"chunked-html-book: navigation drift for {expected['section_id']}",
        )
        require(
            [
                (node.attrib.get("rel"), node.attrib.get("href"))
                for node in top.findall("a")
            ]
            == [
                (node.attrib.get("rel"), node.attrib.get("href"))
                for node in bottom.findall("a")
            ],
            f"chunked-html-book: top/bottom navigation mismatch for {expected['section_id']}",
        )

    require(
        resolve_chunked_xref("ch-system-binutils", "contents-binutils")
        == "binutils.html#contents-binutils",
        "chunked-html-book: same-directory nested xref drift",
    )
    require(
        resolve_chunked_xref("ch-tools-cleanup", "chapter-building-system")
        == "../chapter08/chapter08.html",
        "chunked-html-book: cross-directory chapter xref drift",
    )
    require(
        resolve_chunked_xref("ch-system-zlib", "ch-partitioning-hostreqs")
        == "../chapter02/hostreqs.html",
        "chunked-html-book: cross-directory page xref drift",
    )


def self_test_chunked_html() -> None:
    golden = load_presentation(
        PRESENTATION / "golden" / "chunked-html-packages.json"
    )
    pages = golden.get("pages")
    require(isinstance(pages, dict), "chunked-html: pages must be an object")

    for name in PROOF_PACKAGES:
        require(name in pages, f"chunked-html: missing golden page for {name}")
        actual = chunked_html_snapshot(name)
        require(
            actual == pages[name],
            f"chunked-html: semantic snapshot drift for {name}",
        )

        rendered = ET.fromstring(render_chunked_html_package(name))
        body = rendered.find("body")
        require(body is not None, f"{name}: rendered body missing")
        content_id = package_document(name)["contents_id"]
        require(
            body.find(f"h2[@id='{content_id}']") is not None,
            f"{name}: contents fragment id missing",
        )

        top = body.find("nav[@data-role='top']")
        bottom = body.find("nav[@data-role='bottom']")
        require(
            top is not None
            and bottom is not None
            and [
                (node.attrib.get("rel"), node.attrib.get("href"))
                for node in top.findall("a")
            ]
            == [
                (node.attrib.get("rel"), node.attrib.get("href"))
                for node in bottom.findall("a")
            ],
            f"{name}: top/bottom navigation drift",
        )


def _editorial_block_digest(blocks: list[dict[str, Any]]) -> str:
    import hashlib
    payload = json.dumps(
        blocks,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _count_bootstrap_commands(blocks: list[dict[str, Any]]) -> int:
    count = 0
    for block in blocks:
        if block.get("type") == "bootstrap_command":
            count += 1
        if isinstance(block.get("blocks"), list):
            count += _count_bootstrap_commands(block["blocks"])
        if block.get("type") == "list":
            for item in block["items"]:
                count += _count_bootstrap_commands(item)
        if block.get("type") == "definition_list":
            for entry in block["entries"]:
                count += _count_bootstrap_commands(entry["blocks"])
    return count


def self_test_editorial_slice() -> None:
    golden = load_presentation(
        PRESENTATION / "golden" / "editorial-slice.json"
    )
    expected = golden.get("documents")
    require(
        isinstance(expected, dict) and expected,
        "editorial-slice: missing golden documents",
    )

    for section_id, observation in expected.items():
        editorial = load_editorial_document(section_id)
        require(
            editorial is not None,
            f"{section_id}: missing migrated editorial document",
        )
        require(
            _editorial_block_digest(editorial["blocks"])
            == observation["block_sha256"],
            f"{section_id}: editorial semantic drift",
        )
        require(
            _count_bootstrap_commands(editorial["blocks"])
            == observation["bootstrap_command_count"],
            f"{section_id}: bootstrap command binding drift",
        )

        rendered = ET.fromstring(
            render_chunked_html_document(section_id)
        )
        body = rendered.find("body")
        require(
            body is not None
            and body.attrib.get("data-body-status") == "complete"
            and rendered.find("body/main") is not None,
            f"{section_id}: editorial page did not render complete body",
        )

        actual_targets = [
            node.attrib["data-xref-target"]
            for node in rendered.findall(".//a[@data-xref-target]")
        ]
        require(
            actual_targets == observation["xref_targets"],
            f"{section_id}: xref target drift",
        )

    pass1 = ET.fromstring(
        render_chunked_html_document("ch-tools-binutils-pass1")
    )
    stage = bootstrap_stage("ch-tools-binutils-pass1")
    rendered_commands = [
        node.text or ""
        for node in pass1.findall(".//code[@data-bootstrap-command]")
    ]
    require(
        rendered_commands == stage["commands"],
        "editorial-slice: bootstrap command text/order drift",
    )

    hostreqs = ET.fromstring(
        render_chunked_html_document("ch-partitioning-hostreqs")
    )
    require(
        hostreqs.find(".//aside[@data-kind='warning']//ul") is not None,
        "editorial-slice: mixed paragraph/list flow was flattened",
    )

    technotes = ET.fromstring(
        render_chunked_html_document("ch-tools-toolchaintechnotes")
    )
    require(
        len(technotes.findall(".//table")) == 3,
        "editorial-slice: toolchain tables missing",
    )

    glibc = ET.fromstring(
        render_chunked_html_document("ch-tools-glibc")
    )
    require(
        glibc.find(".//blockquote") is not None,
        "editorial-slice: blockquote missing",
    )
    glibc_stage = bootstrap_stage("ch-tools-glibc")
    require(
        [
            node.text or ""
            for node in glibc.findall(".//code[@data-bootstrap-command]")
        ]
        == glibc_stage["commands"],
        "editorial-slice: Glibc bootstrap command text/order drift",
    )

    pkgmgt = ET.fromstring(
        render_chunked_html_document("ch-system-pkgmgt")
    )
    require(
        pkgmgt.find(".//span[@data-role='footnote']") is not None,
        "editorial-slice: footnote missing",
    )

    afterlfs = ET.fromstring(
        render_chunked_html_document("afterlfs")
    )
    require(
        len(afterlfs.findall(".//kbd[@data-keycombo='true']")) == 5,
        "editorial-slice: key-combination rendering drift",
    )


def self_test_editorial_bulk() -> None:
    golden = load_presentation(
        PRESENTATION / "golden" / "editorial-bulk.json"
    )
    complete = golden.get("complete_documents")
    deferred = golden.get("deferred_command_documents")
    observations = golden.get("documents")
    require(
        isinstance(complete, list)
        and isinstance(deferred, list)
        and isinstance(observations, dict),
        "editorial-bulk: invalid golden manifest",
    )
    require(
        len(complete) == golden.get("complete_document_count") == 89
        and len(deferred) == golden.get("deferred_document_count") == 30,
        "editorial-bulk: migration counts drift",
    )
    require(
        not set(complete).intersection(deferred),
        "editorial-bulk: complete/deferred overlap",
    )

    non_package = {
        document["section_id"]
        for document in compose_book()["documents"]
        if not document.get("package")
    }
    require(
        set(complete).union(deferred) == non_package
        and len(non_package) == 119,
        "editorial-bulk: non-package coverage drift",
    )

    for section_id in complete:
        editorial = load_editorial_document(section_id)
        require(
            editorial is not None,
            f"{section_id}: complete editorial body missing",
        )
        rendered = ET.fromstring(
            render_chunked_html_document(section_id)
        )
        body = rendered.find("body")
        require(
            body is not None
            and body.attrib.get("data-body-status") == "complete",
            f"{section_id}: complete editorial body rendered pending",
        )

    for section_id, observation in observations.items():
        editorial = load_editorial_document(section_id)
        require(editorial is not None, f"{section_id}: bulk body missing")
        require(
            _editorial_block_digest(editorial["blocks"])
            == observation["block_sha256"],
            f"{section_id}: bulk editorial semantic drift",
        )
        rendered = ET.fromstring(
            render_chunked_html_document(section_id)
        )
        actual_targets = [
            node.attrib["data-xref-target"]
            for node in rendered.findall(".//a[@data-xref-target]")
        ]
        require(
            actual_targets == observation["xref_targets"],
            f"{section_id}: bulk xref target drift",
        )
        require(
            _count_bootstrap_commands(editorial["blocks"])
            == observation["bootstrap_command_count"],
            f"{section_id}: bulk bootstrap binding count drift",
        )
        if observation["bootstrap_command_count"]:
            stage = bootstrap_stage(section_id)
            rendered_commands = [
                node.text or ""
                for node in rendered.findall(
                    ".//code[@data-bootstrap-command]"
                )
            ]
            require(
                rendered_commands == stage["commands"],
                f"{section_id}: bulk bootstrap command text/order drift",
            )

    for section_id in deferred:
        require(
            load_editorial_document(section_id) is None,
            f"{section_id}: deferred operational body became presentation authority",
        )
        rendered = ET.fromstring(
            render_chunked_html_document(section_id)
        )
        body = rendered.find("body")
        require(
            body is not None
            and body.attrib.get("data-body-status")
            == "pending-editorial-migration",
            f"{section_id}: deferred operational body lost pending status",
        )


def _canonical_source_command(value: str) -> str:
    import re
    return re.sub(r"[ \t]*\\\r?\n[ \t]*", " ", value.strip())


def _resolved_command_hashes(name: str) -> list[str]:
    import hashlib
    package = resolve([name])["packages"][0]
    return [
        hashlib.sha256(
            _canonical_source_command(
                command.get("source_command", command["command"])
            ).encode()
        ).hexdigest()
        for _step, command in command_sequence(package)
    ]


def self_test_package_bulk() -> None:
    golden = load_presentation(PRESENTATION / "golden" / "chunked-html-packages-all.json")
    complete = golden.get("complete_packages")
    deferred = golden.get("deferred_authority_mismatches")
    observations = golden.get("packages")
    require(isinstance(complete, list) and isinstance(deferred, list) and isinstance(observations, dict), "package-bulk: invalid golden manifest")
    require(len(complete) == golden.get("complete_package_count") == 71 and len(deferred) == golden.get("deferred_package_count") == 9, "package-bulk: package coverage drift")
    package_set = load_json(HERE / "package-set.json")["packages"]
    require(set(complete).union(deferred) == set(package_set) and not set(complete).intersection(deferred), "package-bulk: complete/deferred package split drift")

    for name in complete:
        editorial = load_presentation(PRESENTATION / "editorial" / f"{name}.json")
        require(editorial.get("installed_labels") == observations[name]["installed_labels"], f"{name}: installed source-label drift")
        require(
            editorial.get("installed_term_kinds")
            == observations[name]["installed_term_kinds"],
            f"{name}: installed term-kind drift",
        )
        require(_resolved_command_hashes(name) == observations[name]["command_sha256"], f"{name}: source/normalized command drift")
        rendered = ET.fromstring(render_chunked_html_package(name))
        require(rendered.find("body/dl[@data-role='installed-summary']") is not None, f"{name}: installed summary missing")

    for name in deferred:
        require(not (PRESENTATION / "editorial" / f"{name}.json").is_file(), f"{name}: authority-mismatch package unexpectedly has editorial overlay")
        document = package_book_document(name)
        rendered = ET.fromstring(render_chunked_html_document(document["section_id"]))
        body = rendered.find("body")
        require(body is not None and body.attrib.get("data-body-status") == "pending-editorial-migration", f"{name}: deferred package lost pending status")

    zlib_html = ET.fromstring(render_chunked_html_package("zlib"))
    zlib_labels = [node.text or "" for node in zlib_html.findall("body/dl[@data-role='installed-summary']/dt")]
    require(zlib_labels == ["Installed libraries"], "zlib: source installed label drift")


def self_test() -> None:
    for name in PROOF_PACKAGES:
        self_test_package(name)

    binutils_root = ET.fromstring(render_package("binutils"))
    require(
        binutils_root.find(".//important") is not None,
        "binutils: missing important admonition",
    )
    require(
        len(binutils_root.findall(".//variablelist[@role='editorial-definition-list']")) == 2,
        "binutils: missing parameter explanation lists",
    )
    filenames = [node.text for node in binutils_root.findall(".//filename")]
    require(
        "/usr/lib" in filenames and "/usr/lib64" in filenames,
        "binutils: missing inline filename semantics",
    )
    literals = [node.text for node in binutils_root.findall(".//literal")]
    require(
        "$(exec_prefix)/$(target_alias)" in literals,
        "binutils: missing inline literal semantics",
    )

    self_test_chapter08()
    self_test_book()
    self_test_nested_xrefs()
    self_test_chunked_html()
    self_test_chunked_html_book()
    self_test_editorial_slice()
    self_test_editorial_bulk()
    self_test_package_bulk()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="compile normalized LFS presentation proof"
    )
    parser.add_argument("--package")
    parser.add_argument("--chapter")
    parser.add_argument("--book", action="store_true")
    parser.add_argument("--xref")
    parser.add_argument("--html-package")
    parser.add_argument("--html-book-dir", type=Path)
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
                        "packages": list(PROOF_PACKAGES),
                        "chapter": "chapter08",
                        "book_graph": True,
                        "nested_xrefs": True,
                        "chunked_html_packages": True,
                        "chunked_html_book": True,
                        "generic_editorial_slice": True,
                        "editorial_vocabulary_complete": True,
                        "editorial_bulk_complete": 89,
                        "editorial_operational_deferred": 30,
                        "package_bulk_complete": 71,
                        "package_authority_deferred": 9,
                        "equivalence":
                            "package-semantics-book-routing-editorial-and-package-bulk",
                    },
                    indent=2,
                )
            )
            return 0

        selected_modes = sum(
            bool(value)
            for value in (
                args.package,
                args.chapter,
                args.book,
                args.xref,
                args.html_package,
                args.html_book_dir,
            )
        )
        require(
            selected_modes <= 1,
            "choose only one presentation mode",
        )

        if args.html_book_dir:
            rendered_book = render_chunked_html_book()
            for relative_path, content in rendered_book.items():
                target = args.html_book_dir / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content + "\n", encoding="utf-8")
            print(
                json.dumps(
                    {
                        "status": "success",
                        "documents": len(rendered_book),
                        "output": str(args.html_book_dir),
                    },
                    indent=2,
                )
            )
            return 0
        if args.html_package:
            rendered = render_chunked_html_package(args.html_package)
        elif args.book:
            rendered = render_book_hierarchy()
        elif args.xref:
            rendered = json.dumps(
                resolve_book_xref(args.xref),
                indent=2,
                sort_keys=True,
            )
        elif args.chapter:
            rendered = render_chapter_hierarchy(args.chapter)
        else:
            rendered = render_package(args.package or "zlib")
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
