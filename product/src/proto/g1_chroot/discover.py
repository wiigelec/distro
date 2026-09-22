#!/usr/bin/env python3
from __future__ import annotations

import re
import time
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


def parse_links(url: str) -> list[str]:
    parser = LinkParser()
    parser.feed(fetch_text(url))
    return parser.links


def archive_candidates(package: str, links: list[str]) -> dict:
    candidates = {}
    for href in links:
        filename = urllib.parse.unquote(urllib.parse.urlparse(href).path.rsplit("/", 1)[-1])
        candidate = candidate_from_filename(package, filename)
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
    return candidates


def release_directory(package: str, href: str):
    path = urllib.parse.unquote(urllib.parse.urlparse(href).path)
    if not path.endswith("/"):
        return None
    name = path.rstrip("/").rsplit("/", 1)[-1]
    prefixes = (f"{package}-", f"{package}_")
    prefix = next((value for value in prefixes if name.startswith(value)), None)
    if prefix is None:
        return None
    version = name[len(prefix):]
    if not version or not version[0].isdigit():
        return None
    if any(marker in version.lower() for marker in UNSTABLE_MARKERS):
        return None
    return {"version": version, "href": href}


def discover_stable(package: dict) -> dict:
    candidates = {}
    directories = []
    for attempt in range(3):
        links = parse_links(package["url"])
        candidates = archive_candidates(package["name"], links)
        directories = [
            candidate
            for href in links
            if (candidate := release_directory(package["name"], href)) is not None
        ]
        if candidates or directories:
            break
        if attempt < 2:
            time.sleep(1)

    discovery_url = package["url"]

    direct_version = (
        max(candidates, key=version_key)
        if candidates
        else None
    )
    selected_dir = (
        max(directories, key=lambda item: version_key(item["version"]))
        if directories
        else None
    )
    if (
        selected_dir is not None
        and (
            direct_version is None
            or version_key(selected_dir["version"]) > version_key(direct_version)
        )
    ):
        discovery_url = urllib.parse.urljoin(package["url"], selected_dir["href"])
        candidates = archive_candidates(
            package["name"],
            parse_links(discovery_url),
        )
        candidates = {
            version: candidate
            for version, candidate in candidates.items()
            if version == selected_dir["version"]
        }

    if not candidates:
        raise RuntimeError(
            f"{package['name']}: no stable release archives discovered at {package['url']}"
        )

    selected = max(candidates.values(), key=lambda item: version_key(item["version"]))
    return {
        "name": package["name"],
        "management": package["management"],
        "version": selected["version"],
        "source_url": urllib.parse.urljoin(discovery_url, selected["filename"]),
        "discovery_url": discovery_url,
    }


def discover_package(package: dict) -> dict:
    management = package.get("management")
    if management != "stable":
        raise RuntimeError(
            f"{package.get('name')}: management policy {management!r} is not implemented"
        )
    return discover_stable(package)
