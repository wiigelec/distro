#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "distro-g1-chroot-prototype/1"

METHODS = (
    ("autotools", ("configure",)),
    ("cmake", ("CMakeLists.txt",)),
    ("meson", ("meson.build",)),
    ("cargo", ("Cargo.toml",)),
    ("python", ("pyproject.toml", "setup.py")),
)

DOCUMENTATION = (
    "INSTALL",
    "INSTALL.md",
    "README",
    "README.md",
    "README.txt",
    "doc/INSTALL",
    "doc/README",
    "docs/INSTALL",
    "docs/README",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def safe_extract(archive: Path, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    resolved_root = destination.resolve()
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if target != resolved_root and resolved_root not in target.parents:
                raise RuntimeError(
                    f"source archive member escapes extraction root: {member.name}"
                )
        tar.extractall(destination, filter="data")

    children = list(destination.iterdir())
    top_dirs = [path for path in children if path.is_dir()]
    if len(children) != 1 or len(top_dirs) != 1:
        raise RuntimeError(
            f"{archive.name}: expected exactly one top-level source directory"
        )
    return top_dirs[0]


def detect_method(source: Path) -> tuple[str, list[str]]:
    evidence = []
    for method, markers in METHODS:
        present = [marker for marker in markers if (source / marker).is_file()]
        if present:
            evidence.extend(present)
            return method, evidence
    raise RuntimeError(f"{source}: unable to identify supported build system")


def documentation_evidence(source: Path) -> list[str]:
    return [name for name in DOCUMENTATION if (source / name).is_file()]


def commands_for(package: str, method: str) -> list[str]:
    if method == "autotools":
        configure = 'cd "$BUILD" && "$SRC/configure" --prefix=/usr'
        if package == "ncurses":
            # Learned from upstream INSTALL after runtime closure showed Bash
            # linked against libncursesw.so.6 while the default ncurses build
            # staged only static libraries.
            configure += " --with-shared"
        elif package == "coreutils":
            # Keep the bootstrap closure minimal and deterministic. Coreutils
            # otherwise auto-detects optional G0 libraries and links against
            # them, making the staged G1 payload depend on undeclared host
            # capabilities.
            configure += (
                " --disable-xattr"
                " --disable-acl"
                " --disable-libcap"
                " --without-gmp"
                " --with-openssl=no"
            )
        return [
            configure,
            'cd "$BUILD" && make -j"$JOBS"',
            'cd "$BUILD" && make DESTDIR="$DESTDIR" install',
        ]
    if method == "cmake":
        return [
            'cmake -S "$SRC" -B "$BUILD" -DCMAKE_INSTALL_PREFIX=/usr',
            'cmake --build "$BUILD" --parallel "$JOBS"',
            'DESTDIR="$DESTDIR" cmake --install "$BUILD"',
        ]
    if method == "meson":
        return [
            'meson setup "$BUILD" "$SRC" --prefix=/usr',
            'meson compile -C "$BUILD" -j "$JOBS"',
            'DESTDIR="$DESTDIR" meson install -C "$BUILD"',
        ]
    if method == "cargo":
        return [
            'cd "$SRC" && cargo build --release',
            'echo "cargo install staging requires recipe refinement" >&2; exit 2',
        ]
    if method == "python":
        return [
            'cd "$SRC" && python -m build',
            'echo "python install staging requires recipe refinement" >&2; exit 2',
        ]
    raise RuntimeError(f"unsupported build method: {method}")


def derive_recipe(resolved: dict, output_root: Path) -> dict:
    package = resolved["name"]
    version = resolved["version"]
    source_url = resolved["source_url"]

    parsed = urllib.parse.urlparse(source_url)
    filename = Path(parsed.path).name
    if not filename:
        raise RuntimeError(f"{package}: source URL has no archive filename")

    archive = output_root / "sources" / filename
    print(f"==> {package}: fetch {source_url}", flush=True)
    download(source_url, archive)
    checksum = sha256_file(archive)

    extract_root = output_root / "work" / f"{package}-{version}" / "unpack"
    source = safe_extract(archive, extract_root)

    method, markers = detect_method(source)
    docs = documentation_evidence(source)

    recipe = {
        "schema_version": 1,
        "candidate": True,
        "identity": {
            "name": package,
            "version": version,
            "architecture": "x86_64",
            "revision": "r1",
        },
        "source": {
            "url": source_url,
            "sha256": checksum,
        },
        "discovery": {
            "management": resolved["management"],
            "discovery_url": resolved["discovery_url"],
            "build_method": method,
            "method_evidence": markers,
            "documentation_evidence": docs,
        },
        "build": {
            "system": method,
            "commands": commands_for(package, method),
        },
    }

    recipe_dir = output_root / "recipes"
    recipe_dir.mkdir(parents=True, exist_ok=True)
    recipe_path = recipe_dir / f"{package}.json"
    recipe_path.write_text(
        json.dumps(recipe, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return {
        "name": package,
        "version": version,
        "source_url": source_url,
        "source_sha256": checksum,
        "build_system": method,
        "method_evidence": markers,
        "documentation_evidence": docs,
        "recipe": str(recipe_path),
    }
