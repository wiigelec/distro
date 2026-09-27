#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

USER_AGENT = "distro-g1-chroot-prototype/1"
ARCHIVE_SUFFIXES = (".tar.xz", ".tar.gz", ".tar.bz2")
UNSTABLE_MARKERS = (
    "alpha",
    "beta",
    "devel",
    "development",
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


def fetch_text(
    url: str,
    *,
    attempts: int = 4,
    timeout: int = 60,
) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except (OSError, urllib.error.URLError) as error:
            if attempt == attempts:
                raise
            delay = 2 ** (attempt - 1)
            print(
                f"==> discovery retry {attempt}/{attempts - 1} "
                f"after {error}; sleeping {delay}s",
                flush=True,
            )
            time.sleep(delay)

    raise RuntimeError(f"unreachable discovery retry state for {url}")


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
    stem_lower = stem.lower()
    prefixes = (f"{package}-", f"{package}_")
    prefix = next(
        (value for value in prefixes if stem_lower.startswith(value.lower())),
        None,
    )
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


def python_release_directory(href: str):
    path = urllib.parse.unquote(urllib.parse.urlparse(href).path)
    if not path.endswith("/"):
        return None
    version = path.rstrip("/").rsplit("/", 1)[-1]
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", version) is None:
        return None
    return {"version": version, "href": href}


def discover_python_stable(package: dict) -> dict:
    directories = []
    for attempt in range(3):
        links = parse_links(package["url"])
        directories = [
            candidate
            for href in links
            if (candidate := python_release_directory(href)) is not None
        ]
        if directories:
            break
        if attempt < 2:
            time.sleep(1)

    for selected_dir in sorted(
        directories,
        key=lambda item: version_key(item["version"]),
        reverse=True,
    ):
        discovery_url = urllib.parse.urljoin(package["url"], selected_dir["href"])
        candidates = archive_candidates("python", parse_links(discovery_url))
        candidate = candidates.get(selected_dir["version"])
        if candidate is None:
            continue
        return {
            "name": package["name"],
            "management": package["management"],
            "version": candidate["version"],
            "source_url": urllib.parse.urljoin(
                discovery_url,
                candidate["filename"],
            ),
            "discovery_url": discovery_url,
        }

    raise RuntimeError(
        f"python: no stable release archives discovered at {package['url']}"
    )



def discover_github_stable(package: dict) -> dict:
    releases = json.loads(fetch_text(package["url"]))
    if not isinstance(releases, list):
        raise RuntimeError(
            f"{package['name']}: expected GitHub releases array at {package['url']}"
        )

    candidates = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not tag:
            continue
        version = tag[1:] if tag.startswith("v") else tag
        if not version or not version[0].isdigit():
            continue
        if any(marker in version.lower() for marker in UNSTABLE_MARKERS):
            continue

        source_url = None
        for asset in release.get("assets", []):
            name = asset.get("name")
            url = asset.get("browser_download_url")
            if not isinstance(name, str) or not isinstance(url, str):
                continue
            candidate = candidate_from_filename(package["name"], name)
            if candidate is not None and candidate["version"] == version:
                source_url = url
                break

        if source_url is None:
            html_url = release.get("html_url")
            if not isinstance(html_url, str) or "/releases/" not in html_url:
                continue
            repository_url = html_url.split("/releases/", 1)[0]
            quoted_tag = urllib.parse.quote(tag, safe="")
            source_url = f"{repository_url}/archive/refs/tags/{quoted_tag}.tar.gz"

        candidates.append(
            {
                "version": version,
                "source_url": source_url,
            }
        )

    if not candidates:
        parsed = urllib.parse.urlparse(package["url"])
        path = parsed.path
        if not path.endswith("/releases"):
            raise RuntimeError(
                f"{package['name']}: unsupported GitHub discovery URL "
                f"{package['url']}"
            )

        tags_url = urllib.parse.urlunparse(
            parsed._replace(path=path[:-len("/releases")] + "/tags", query="per_page=100")
        )
        tags = json.loads(fetch_text(tags_url))
        if not isinstance(tags, list):
            raise RuntimeError(
                f"{package['name']}: expected GitHub tags array at {tags_url}"
            )

        repository_path = path[:-len("/releases")]
        repository_url = f"https://github.com{repository_path.removeprefix('/repos')}"
        for tag_record in tags:
            tag = tag_record.get("name")
            if not isinstance(tag, str) or not tag:
                continue
            version = tag[1:] if tag.startswith("v") else tag
            if not version or not version[0].isdigit():
                continue
            if any(marker in version.lower() for marker in UNSTABLE_MARKERS):
                continue

            quoted_tag = urllib.parse.quote(tag, safe="")
            candidates.append(
                {
                    "version": version,
                    "source_url": (
                        f"{repository_url}/archive/refs/tags/{quoted_tag}.tar.gz"
                    ),
                }
            )

    if not candidates:
        raise RuntimeError(
            f"{package['name']}: no stable GitHub releases or tags discovered at "
            f"{package['url']}"
        )

    selected = max(candidates, key=lambda item: version_key(item["version"]))
    return {
        "name": package["name"],
        "management": package["management"],
        "version": selected["version"],
        "source_url": selected["source_url"],
        "discovery_url": package["url"],
    }


def discover_stable(package: dict) -> dict:
    if package["name"] in {"python", "python-binascii"}:
        return discover_python_stable(package)
    if urllib.parse.urlparse(package["url"]).hostname == "api.github.com":
        return discover_github_stable(package)

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
