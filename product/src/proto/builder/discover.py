#!/usr/bin/env python3

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

USER_AGENT = "distro-builder-prototype/0"
DOC_NAMES = ("BUILD", "INSTALL", "README", "CONTRIBUTING", "HACKING")


def github_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def parse_github_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.lower() != "github.com":
        raise ValueError("prototype currently supports github.com URLs only")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("URL must identify owner/repository")

    repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    return parts[0], repo


def latest_version(owner, repo):
    base = f"https://api.github.com/repos/{owner}/{repo}"

    try:
        release = github_json(f"{base}/releases/latest")
        tag = release["tag_name"]
        return {"version": tag, "ref": tag, "source": "github-release"}
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise

    tags = github_json(f"{base}/tags?per_page=100")
    if not tags:
        raise RuntimeError("no releases or tags found")

    tag = tags[0]["name"]
    return {"version": tag, "ref": tag, "source": "github-tag"}


def repository_tree(owner, repo, ref):
    base = f"https://api.github.com/repos/{owner}/{repo}"
    encoded_ref = urllib.parse.quote(ref, safe="")
    commit = github_json(f"{base}/commits/{encoded_ref}")
    tree_sha = commit["commit"]["tree"]["sha"]
    tree = github_json(f"{base}/git/trees/{tree_sha}?recursive=1")

    return [
        item["path"]
        for item in tree.get("tree", [])
        if item.get("type") == "blob"
    ]


def read_file(owner, repo, ref, path):
    encoded_ref = urllib.parse.quote(ref, safe="")
    encoded_path = "/".join(
        urllib.parse.quote(part, safe="")
        for part in path.split("/")
    )
    url = (
        f"https://raw.githubusercontent.com/"
        f"{owner}/{repo}/{encoded_ref}/{encoded_path}"
    )

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(500000).decode("utf-8", errors="replace")


def documentation_paths(paths):
    ranked = []

    for path in paths:
        base = PurePosixPath(path).name.upper()
        upper = path.upper()

        priority = None
        for index, name in enumerate(DOC_NAMES):
            if base.startswith(name):
                priority = index
                break

        if priority is None and upper.startswith(("DOC/", "DOCS/")):
            priority = 10

        if priority is not None:
            ranked.append((priority, path.count("/"), path))

    ranked.sort()
    return [path for _, _, path in ranked[:20]]


def extract_commands(path, text):
    heading = ""
    relevant = False
    in_fence = False
    commands = []

    heading_re = re.compile(
        r"\b(build|building|compile|compiling|install|installation|source|development)\b",
        re.I,
    )

    command_re = re.compile(
        r"^\s*(?:\$ )?(?:"
        r"\./(?:configure|autogen\.sh|buildconf)|"
        r"autoreconf\b|cmake\b|meson\b|ninja\b|make\b|"
        r"cargo\b|go\b|python(?:3)?\b|pip(?:3)?\b"
        r")"
    )

    for raw in text.splitlines():
        line = raw.rstrip()

        match = re.match(r"^\s{0,3}#{1,6}\s+(.+)$", line)
        if match and not in_fence:
            heading = match.group(1)
            relevant = bool(heading_re.search(heading))
            continue

        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue

        if not relevant:
            continue

        if command_re.match(line):
            command = line.strip()
            if command.startswith("$ "):
                command = command[2:]

            commands.append({
                "command": command,
                "source": f"{path}#{heading or 'document'}"
            })

    return commands


def documented_discovery(owner, repo, ref, paths):
    commands = []
    evidence = []

    for path in documentation_paths(paths):
        try:
            text = read_file(owner, repo, ref, path)
        except Exception as exc:
            evidence.append({
                "kind": "documentation-error",
                "source": path,
                "detail": str(exc)
            })
            continue

        found = extract_commands(path, text)
        if found:
            commands.extend(found)
            evidence.append({
                "kind": "documentation",
                "source": path,
                "detail": f"found {len(found)} build command(s)"
            })

    unique = []
    seen = set()
    for command in commands:
        key = command["command"]
        if key not in seen:
            seen.add(key)
            unique.append(command)

    return unique, evidence


def infer_build(paths):
    names = {PurePosixPath(path).name for path in paths}

    cases = [
        (
            "cmake",
            {"CMakeLists.txt"},
            ["cmake", "cc"],
            [
                "cmake -S . -B build -DCMAKE_INSTALL_PREFIX=/usr",
                "cmake --build build",
                'DESTDIR="$DESTDIR" cmake --install build'
            ]
        ),
        (
            "meson",
            {"meson.build"},
            ["meson", "ninja", "cc"],
            [
                "meson setup build --prefix=/usr",
                "meson compile -C build",
                'DESTDIR="$DESTDIR" meson install -C build'
            ]
        ),
        (
            "autotools",
            {"configure.ac", "configure.in"},
            ["autoconf", "automake", "make", "cc"],
            [
                "autoreconf -fi",
                "./configure --prefix=/usr",
                "make",
                'make DESTDIR="$DESTDIR" install'
            ]
        ),
        (
            "cargo",
            {"Cargo.toml"},
            ["cargo", "rustc"],
            ["cargo build --release"]
        ),
        (
            "go",
            {"go.mod"},
            ["go"],
            ["go build ./..."]
        ),
        (
            "make",
            {"Makefile", "GNUmakefile", "makefile"},
            ["make", "cc"],
            ["make", 'make DESTDIR="$DESTDIR" install']
        )
    ]

    for system, markers, tools, commands in cases:
        matched = sorted(markers & names)
        if matched:
            return {
                "source": "inferred",
                "status": "partial",
                "system": system,
                "required_tools": tools,
                "commands": [
                    {"command": command, "source": "structural-fallback"}
                    for command in commands
                ],
                "evidence": [
                    {
                        "kind": "source-tree",
                        "source": marker,
                        "detail": f"{system} build marker"
                    }
                    for marker in matched
                ]
            }

    return {
        "source": "unknown",
        "status": "needs-review",
        "system": None,
        "required_tools": [],
        "commands": [],
        "evidence": []
    }


def discover(package):
    owner, repo = parse_github_url(package["url"])
    version = latest_version(owner, repo)
    paths = repository_tree(owner, repo, version["ref"])

    commands, evidence = documented_discovery(
        owner,
        repo,
        version["ref"],
        paths
    )

    if commands:
        build = {
            "source": "documentation",
            "status": "success",
            "commands": commands
        }
    else:
        build = infer_build(paths)
        evidence.extend(build.pop("evidence"))

    return {
        "name": package["name"],
        "url": package["url"],
        "version": version,
        "build": build,
        "evidence": evidence
    }


def load_manifest(path):
    manifest = json.loads(Path(path).read_text())
    packages = manifest.get("packages")

    if not isinstance(packages, list) or not packages:
        raise ValueError("manifest must contain a non-empty packages array")

    for package in packages:
        if not package.get("name") or not package.get("url"):
            raise ValueError("each package requires name and url")

    return packages


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()

    result = {
        "packages": [
            discover(package)
            for package in load_manifest(args.manifest)
        ]
    }

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
