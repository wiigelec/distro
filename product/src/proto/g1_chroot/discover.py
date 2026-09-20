#!/usr/bin/env python3
from __future__ import annotations

import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

USER_AGENT = "distro-g1-chroot-prototype/1"
ARCHIVE_SUFFIXES = (".tar.xz", ".tar.gz", ".tar.bz2")
UNSTABLE_MARKERS = (
    "alpha",
    "beta",
    "pre",
    "preview",
    "rc",
    "snapshot",
    "test",
)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def version_key(version: str):
    parts = re.split(r"([0-9]+)", version)
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in parts
        if part
    )


def candidate_from_filename(package: str, filename: str):
    lower = filename.lower()
    suffix = next((value for value in ARCHIVE_SUFFIXES if lower.endswith(value)), None)
    if suffix is None:
        return None

    stem = filename[:-len(suffix)]
    prefixes = (f"{package}-", f"{package}_")
    prefix = next((value for value in prefixes if stem.startswith(value)), None)
    if prefix is None:
        return None

    version = stem[len(prefix):]

    # Release archives must begin immediately with a numeric version. This
    # excludes auxiliary archives such as bash-doc-*, readline-doc-*, and
    # glibc-ports-* without package-specific deny lists.
    if not version or not version[0].isdigit():
        return None

    if any(marker in version.lower() for marker in UNSTABLE_MARKERS):
        return None

    return {
        "version": version,
        "filename": filename,
    }


def discover_stable(package: dict) -> dict:
    parser = LinkParser()
    parser.feed(fetch_text(package["url"]))

    candidates = {}
    for href in parser.links:
        filename = urllib.parse.unquote(urllib.parse.urlparse(href).path.rsplit("/", 1)[-1])
        candidate = candidate_from_filename(package["name"], filename)
        if candidate is None:
            continue
        current = candidates.get(candidate["version"])
        if current is None:
            candidates[candidate["version"]] = candidate
            continue
        preferred = sorted(
            (current, candidate),
            key=lambda item: ARCHIVE_SUFFIXES.index(
                next(s for s in ARCHIVE_SUFFIXES if item["filename"].endswith(s))
            ),
        )[0]
        candidates[candidate["version"]] = preferred

    if not candidates:
        raise RuntimeError(
            f"{package['name']}: no stable release archives discovered at {package['url']}"
        )

    selected = max(candidates.values(), key=lambda item: version_key(item["version"]))
    return {
        "name": package["name"],
        "management": package["management"],
        "version": selected["version"],
        "source_url": urllib.parse.urljoin(package["url"], selected["filename"]),
        "discovery_url": package["url"],
    }


def discover_package(package: dict) -> dict:
    management = package.get("management")
    if management != "stable":
        raise RuntimeError(
            f"{package.get('name')}: management policy {management!r} is not implemented"
        )
    return discover_stable(package)
