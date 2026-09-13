#!/usr/bin/env python3

import argparse
import json
import re
import shlex
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

USER_AGENT = "distro-builder-prototype/0"
DOC_NAMES = ("BUILD", "INSTALL", "README", "CONTRIBUTING", "HACKING")

BUILD_HEADING_RE = re.compile(
    r"\b(build|building|compile|compiling|configure|configuring|"
    r"install|installation|source|development|developer)\b",
    re.I,
)

COMMAND_START_RE = re.compile(
    r"^(?:"
    r"\./(?:configure|autogen\.sh|buildconf)|"
    r"autoreconf(?:\s|$)|"
    r"cmake(?:\s|$)|"
    r"meson(?:\s|$)|"
    r"ninja(?:\s|$)|"
    r"make(?:\s|$)|"
    r"cargo(?:\s|$)|"
    r"go(?:\s|$)|"
    r"python(?:3)?(?:\s|$)|"
    r"pip(?:3)?(?:\s|$)"
    r")"
)

PHASE_ORDER = ("bootstrap", "configure", "build", "test", "install")


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


def authoritative_build_document(path):
    base = PurePosixPath(path).name.upper()
    return base.startswith(("BUILD", "INSTALL"))


def document_system_hint(path):
    base = PurePosixPath(path).name.upper()
    if "CMAKE" in base:
        return "cmake"
    if "MESON" in base:
        return "meson"
    return None


def normalize_command(line):
    command = line.strip()
    if command.startswith("$ "):
        command = command[2:].lstrip()
    return command


def is_command_line(raw_line, in_fence, relevant_context):
    if not relevant_context:
        return False

    stripped = raw_line.strip()
    if not stripped:
        return False

    explicit_shell_form = (
        in_fence
        or raw_line.startswith(("    ", "\t"))
        or stripped.startswith("$ ")
    )
    if not explicit_shell_form:
        return False

    command = normalize_command(raw_line)
    return bool(COMMAND_START_RE.match(command))


def join_continuations(lines, start):
    command = normalize_command(lines[start])
    index = start

    while command.rstrip().endswith("\\") and index + 1 < len(lines):
        index += 1
        next_part = lines[index].strip()
        if next_part.startswith("$ "):
            next_part = next_part[2:].lstrip()
        command = command.rstrip()[:-1].rstrip() + " " + next_part

    return command, index


def normalize_documented_command(command):
    normalized = command.strip()
    optional = False
    alternatives = []

    optional_match = re.search(r"\s*\(optional\)\s*$", normalized, re.I)
    if optional_match:
        normalized = normalized[:optional_match.start()].rstrip()
        optional = True

    bracket_match = re.search(r"\s+\[([^\]]+)\]\s*$", normalized)
    if bracket_match:
        tokens = bracket_match.group(1).split()
        if tokens and all(token.startswith("--") for token in tokens):
            alternatives = tokens
            normalized = normalized[:bracket_match.start()].rstrip()

    return normalized, optional, alternatives


def classify_phase(command):
    lowered = command.lower()

    if lowered.startswith(("./autogen.sh", "./buildconf", "autoreconf ")):
        return "bootstrap"
    if lowered.startswith("./configure"):
        return "configure"
    if lowered.startswith("cmake "):
        if " --install " in f" {lowered} ":
            return "install"
        if " --build " in f" {lowered} ":
            return "build"
        return "configure"
    if lowered.startswith("meson setup"):
        return "configure"
    if lowered.startswith("meson compile"):
        return "build"
    if lowered.startswith("meson install"):
        return "install"
    if lowered.startswith(("make test", "make check", "ninja test")):
        return "test"
    if lowered.startswith("make"):
        return "install" if re.search(r"\binstall\b", lowered) else "build"
    if lowered.startswith(("cargo build", "go build")):
        return "build"
    if lowered.startswith(("pip install", "pip3 install", "python -m pip install", "python3 -m pip install")):
        return "install"

    return "build"


def classify_system(command, path_hint=None, current_system=None):
    lowered = command.lower()

    if lowered.startswith("cmake "):
        return "cmake"
    if lowered.startswith(("meson ", "ninja ")):
        return "meson"
    if lowered.startswith(("./configure", "./autogen.sh", "./buildconf", "autoreconf ")):
        return "autotools"
    if lowered.startswith("cargo "):
        return "cargo"
    if lowered.startswith("go "):
        return "go"
    if lowered.startswith(("python ", "python3 ", "pip ", "pip3 ")):
        return "python"
    if lowered.startswith("make"):
        return current_system or path_hint or "make"

    return current_system or path_hint


def command_tool(command):
    try:
        words = shlex.split(command)
    except ValueError:
        return None

    if not words:
        return None

    first = words[0]
    if first in {"cmake", "meson", "ninja", "make", "cargo", "go", "python", "python3", "pip", "pip3"}:
        return first
    if first in {"autoreconf"}:
        return first
    return None


def extract_document_commands(path, text):
    authoritative = authoritative_build_document(path)
    path_hint = document_system_hint(path)

    lines = text.splitlines()
    commands = []
    heading = ""
    heading_relevant = authoritative
    in_fence = False
    fence_relevant = False
    current_system = path_hint
    index = 0

    while index < len(lines):
        raw_line = lines[index]

        heading_match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", raw_line)
        if heading_match and not in_fence:
            heading = heading_match.group(1)
            heading_relevant = authoritative or bool(BUILD_HEADING_RE.search(heading))
            index += 1
            continue

        if raw_line.lstrip().startswith("```"):
            if in_fence:
                in_fence = False
                fence_relevant = False
            else:
                in_fence = True
                fence_relevant = heading_relevant
            index += 1
            continue

        relevant_context = heading_relevant or fence_relevant

        if is_command_line(raw_line, in_fence, relevant_context):
            raw_command, end_index = join_continuations(lines, index)
            command, optional, alternatives = normalize_documented_command(raw_command)
            system = classify_system(command, path_hint, current_system)
            if system:
                current_system = system

            record = {
                "system": system,
                "phase": classify_phase(command),
                "command": command,
                "source": f"{path}#{heading or 'document'}",
            }
            if optional:
                record["optional"] = True
            if alternatives:
                record["alternatives"] = alternatives

            commands.append(record)
            index = end_index + 1
            continue

        index += 1

    return commands


def cmake_directory(command, option):
    try:
        words = shlex.split(command)
    except ValueError:
        return None

    if option == "-B":
        for index, word in enumerate(words):
            if word == "-B" and index + 1 < len(words):
                return words[index + 1]
            if word.startswith("-B") and len(word) > 2:
                return word[2:]
        return None

    if option in {"--build", "--install"}:
        try:
            index = words.index(option)
        except ValueError:
            return None
        return words[index + 1] if index + 1 < len(words) else None

    return None


def select_configure_command(records, method_items):
    if not records:
        return None

    if records[0]["system"] == "cmake":
        target_directories = []
        for item in method_items:
            if item["phase"] == "build":
                directory = cmake_directory(item["command"], "--build")
            elif item["phase"] == "install":
                directory = cmake_directory(item["command"], "--install")
            else:
                directory = None

            if directory and directory not in target_directories:
                target_directories.append(directory)

        for directory in target_directories:
            for item in records:
                if cmake_directory(item["command"], "-B") == directory:
                    return item

        out_of_tree = [
            item for item in records
            if (cmake_directory(item["command"], "-B") or ".") not in {".", "./"}
        ]
        if out_of_tree:
            return out_of_tree[0]

    return records[0]


def build_methods(commands):
    by_system = {}

    for item in commands:
        system = item.get("system")
        if not system:
            continue
        by_system.setdefault(system, []).append(item)

    methods = []

    for system, items in by_system.items():
        selected = []

        for phase in PHASE_ORDER:
            phase_items = [item for item in items if item["phase"] == phase]
            if not phase_items:
                continue

            if phase == "configure":
                chosen = select_configure_command(phase_items, items)
            else:
                chosen = phase_items[0]

            if chosen:
                selected.append(chosen)

        if not selected:
            continue

        tools = []
        for item in selected:
            tool = command_tool(item["command"])
            if tool and tool not in tools:
                tools.append(tool)

        sources = []
        for item in selected:
            if item["source"] not in sources:
                sources.append(item["source"])

        command_records = []
        for item in selected:
            command_record = {
                "phase": item["phase"],
                "command": item["command"],
                "source": item["source"],
            }
            if item.get("optional"):
                command_record["optional"] = True
            if item.get("alternatives"):
                command_record["alternatives"] = item["alternatives"]
            command_records.append(command_record)

        methods.append({
            "system": system,
            "documented_tools": tools,
            "commands": command_records,
            "sources": sources,
        })

    methods.sort(key=lambda item: item["system"])
    return methods


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

        found = extract_document_commands(path, text)
        if found:
            commands.extend(found)
            evidence.append({
                "kind": "documentation",
                "source": path,
                "detail": f"found {len(found)} shell command(s)"
            })

    methods = build_methods(commands)
    return methods, evidence


def infer_build(paths):
    names = {PurePosixPath(path).name for path in paths}

    cases = [
        (
            "cmake",
            {"CMakeLists.txt"},
            ["cmake", "cc"],
            [
                ("configure", "cmake -S . -B build -DCMAKE_INSTALL_PREFIX=/usr"),
                ("build", "cmake --build build"),
                ("install", 'DESTDIR="$DESTDIR" cmake --install build')
            ]
        ),
        (
            "meson",
            {"meson.build"},
            ["meson", "ninja", "cc"],
            [
                ("configure", "meson setup build --prefix=/usr"),
                ("build", "meson compile -C build"),
                ("install", 'DESTDIR="$DESTDIR" meson install -C build')
            ]
        ),
        (
            "autotools",
            {"configure.ac", "configure.in"},
            ["autoconf", "automake", "make", "cc"],
            [
                ("bootstrap", "autoreconf -fi"),
                ("configure", "./configure --prefix=/usr"),
                ("build", "make"),
                ("install", 'make DESTDIR="$DESTDIR" install')
            ]
        ),
        (
            "cargo",
            {"Cargo.toml"},
            ["cargo", "rustc"],
            [("build", "cargo build --release")]
        ),
        (
            "go",
            {"go.mod"},
            ["go"],
            [("build", "go build ./...")]
        ),
        (
            "make",
            {"Makefile", "GNUmakefile", "makefile"},
            ["make", "cc"],
            [
                ("build", "make"),
                ("install", 'make DESTDIR="$DESTDIR" install')
            ]
        )
    ]

    for system, markers, tools, commands in cases:
        matched = sorted(markers & names)
        if matched:
            return {
                "source": "inferred",
                "status": "partial",
                "methods": [{
                    "system": system,
                    "inferred_tools": tools,
                    "commands": [
                        {
                            "phase": phase,
                            "command": command,
                            "source": "structural-fallback"
                        }
                        for phase, command in commands
                    ],
                    "sources": ["structural-fallback"],
                }],
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
        "methods": [],
        "evidence": []
    }


def discover(package):
    owner, repo = parse_github_url(package["url"])
    version = latest_version(owner, repo)
    paths = repository_tree(owner, repo, version["ref"])

    methods, evidence = documented_discovery(
        owner,
        repo,
        version["ref"],
        paths
    )

    if methods:
        build = {
            "source": "documentation",
            "status": "success",
            "methods": methods
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
