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
    if method == "linux-headers":
        return [
            'cd "$SRC" && make -j"$JOBS" headers_install INSTALL_HDR_PATH="$DESTDIR/usr"',
        ]
    if method == "autotools":
        configure = 'cd "$BUILD" && "$SRC/configure" --prefix=/usr'
        if package == "gmp":
            # GMP 6.3.0's compiler probe is not C23-clean. GCC 15 defaults
            # to gnu23, so force the older GNU C dialect expected by the
            # upstream configure test while leaving GMP's ABI/optimization
            # selection intact.
            configure = (
                'cd "$BUILD" && CC="gcc -std=gnu17" "$SRC/configure"'
                " --prefix=/usr --libdir=/usr/lib64"
            )
        elif package in ("mpfr", "mpc"):
            # Keep bootstrap shared libraries on the loader-visible x86_64
            # runtime path used by the G1 root.
            configure += " --libdir=/usr/lib64"
        elif package == "ncurses":
            # Learned from upstream INSTALL after runtime closure showed Bash
            # linked against libncursesw.so.6 while the default ncurses build
            # staged only static libraries.
            configure += " --with-shared --with-versioned-syms --libdir=/usr/lib64"
        elif package == "binutils":
            # Avoid optional G0 integrations in the bootstrap toolchain.
            configure += (
                " --disable-gprofng"
                " --without-zstd"
                " --without-debuginfod"
            )
        elif package == "make":
            # Guile support is optional and otherwise auto-detects host Guile
            # and its garbage collector.
            configure += " --without-guile"
        elif package == "gcc":
            # Build the native bootstrap compiler without a three-stage GCC
            # bootstrap and without 32-bit multilib requirements.
            configure += (
                " --disable-bootstrap"
                " --disable-multilib"
                " --enable-languages=c,c++"
                " --without-isl"
                " --without-zstd"
            )
        elif package == "gawk":
            # Readline is optional for gawk's interactive debugger. Avoid
            # auto-detecting the G0 library in the bootstrap build.
            configure += " --without-readline"
        elif package == "bison":
            # libtextstyle is optional, but the prefix switch alone still
            # permits system discovery. Force the configure cache result to
            # no so the bootstrap build cannot link a G0 libtextstyle.
            configure = (
                'cd "$BUILD" && ac_cv_libtextstyle=no "$SRC/configure"'
                " --prefix=/usr"
            )
        elif package == "grep":
            # PCRE2 support is optional and otherwise auto-detects the G0
            # library, introducing an undeclared runtime dependency.
            configure += " --disable-perl-regexp"
        elif package == "rsync":
            # Rsync bundles popt and can operate without these optional
            # host integrations. Keep the bootstrap package self-contained
            # instead of linking against G0-only libraries.
            configure += (
                " --with-included-popt"
                " --disable-acl-support"
                " --disable-xattr-support"
                " --disable-openssl"
                " --disable-xxhash"
                " --disable-zstd"
                " --disable-lz4"
                " --disable-idn"
            )
        elif package == "sed":
            # Sed's ACL/xattr support is optional. Disable host-detected
            # integrations so the bootstrap package does not acquire
            # undeclared libacl/libattr runtime dependencies.
            configure += " --disable-acl --disable-xattr"
        elif package == "coreutils":
            # Keep the bootstrap closure minimal and deterministic. Coreutils
            # otherwise auto-detects optional G0 libraries and links against
            # them, making the staged G1 payload depend on undeclared host
            # capabilities.
            configure += (
                " --disable-xattr"
                " --disable-acl"
                " --disable-libcap"
                " --without-libgmp"
                " --with-openssl=no"
            )
        if package == "binutils":
            # arlex.l provides yywrap itself, so the Flex runtime library
            # detected by configure is unnecessary. Override LEXLIB only for
            # Binutils to avoid a libfl runtime dependency in ar and ranlib.
            return [
                configure,
                'cd "$BUILD" && make -j"$JOBS" LEXLIB=',
                'cd "$BUILD" && make DESTDIR="$DESTDIR" LEXLIB= install',
            ]
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

    if (
        package == "linux"
        and (source / "Makefile").is_file()
        and (source / "include/uapi/linux").is_dir()
    ):
        method = "linux-headers"
        markers = ["Makefile", "include/uapi/linux"]
    else:
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
