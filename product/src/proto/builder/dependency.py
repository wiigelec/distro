"""Prototype documentation-first build dependency discovery and resolution."""

from __future__ import annotations

import re

from discover import (
    documentation_paths,
    parse_github_url,
    read_file,
    repository_tree,
)


# Capability names are upstream-facing. Debian package names are resolver output.
# The rules intentionally identify capabilities from upstream release docs rather
# than treating distro package names as discovery facts.
CURL_CAPABILITY_RULES = [
    {
        "capability": "tls.openssl",
        "patterns": (r"--with-openssl\b", r"\bOpenSSL\b"),
        "debian": "libssl-dev",
    },
    {
        "capability": "compression.zlib",
        "patterns": (r"--without-zlib\b", r"\bzlib\b"),
        "debian": "zlib1g-dev",
    },
    {
        "capability": "cookies.libpsl",
        "patterns": (r"--without-libpsl\b", r"\blibpsl\b"),
        "debian": "libpsl-dev",
    },
    {
        "capability": "compression.brotli",
        "patterns": (r"--without-brotli\b", r"\bBrotli\b"),
        "debian": "libbrotli-dev",
    },
    {
        "capability": "compression.zstd",
        "patterns": (r"--without-zstd\b", r"\bZstd\b", r"\bzstd\b"),
        "debian": "libzstd-dev",
    },
    {
        "capability": "http2.nghttp2",
        "patterns": (r"--without-nghttp2\b", r"\bnghttp2\b"),
        "debian": "libnghttp2-dev",
    },
    {
        "capability": "idn.libidn2",
        "patterns": (r"--without-libidn2\b", r"\blibidn2\b"),
        "debian": "libidn2-dev",
    },
    {
        "capability": "ssh.libssh2",
        "patterns": (r"--with-libssh2\b", r"\blibssh2\b"),
        "debian": "libssh2-1-dev",
    },
]


DEBIAN_BUILD_SYSTEM_PACKAGES = {
    "cmake": ["build-essential", "cmake", "pkg-config"],
    "meson": ["build-essential", "meson", "ninja-build", "pkg-config"],
    "autotools": ["build-essential", "autoconf", "automake", "libtool", "pkg-config"],
    "make": ["build-essential"],
}


def evidence_lines(text, patterns):
    evidence = []
    compiled = [re.compile(pattern, re.I) for pattern in patterns]

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern.search(stripped) for pattern in compiled):
            evidence.append({
                "line": line_number,
                "text": stripped[:240],
            })
            if len(evidence) >= 3:
                break

    return evidence


def discover_curl_capabilities(discovery):
    owner, repo = parse_github_url(discovery["url"])
    ref = discovery["version"]["ref"]
    paths = repository_tree(owner, repo, ref)

    documents = []
    for path in documentation_paths(paths):
        try:
            text = read_file(owner, repo, ref, path)
        except Exception:
            continue
        documents.append((path, text))

    capabilities = []
    for rule in CURL_CAPABILITY_RULES:
        evidence = []
        for path, text in documents:
            matches = evidence_lines(text, rule["patterns"])
            if matches:
                evidence.append({
                    "source": path,
                    "matches": matches,
                })

        if evidence:
            capabilities.append({
                "name": rule["capability"],
                "classification": "documented-feature-capability",
                "evidence": evidence,
            })

    return capabilities


def resolve_debian(build_system, capabilities):
    try:
        packages = list(DEBIAN_BUILD_SYSTEM_PACKAGES[build_system])
    except KeyError as exc:
        raise ValueError(
            f"no Debian build-tool resolver policy for {build_system}"
        ) from exc

    capability_packages = []
    rules = {rule["capability"]: rule for rule in CURL_CAPABILITY_RULES}

    for capability in capabilities:
        name = capability["name"]
        rule = rules.get(name)
        if not rule:
            continue
        package = rule["debian"]
        capability_packages.append({
            "capability": name,
            "package": package,
        })
        if package not in packages:
            packages.append(package)

    return {
        "distribution": "debian",
        "distribution_version": "12",
        "build_system": build_system,
        "build_tool_packages": list(DEBIAN_BUILD_SYSTEM_PACKAGES[build_system]),
        "capability_packages": capability_packages,
        "packages": packages,
    }


def discover_dependencies(discovery, build_system):
    if discovery["name"] != "curl":
        raise ValueError(
            "prototype capability discovery currently implements curl only"
        )

    capabilities = discover_curl_capabilities(discovery)
    resolution = resolve_debian(build_system, capabilities)

    return {
        "schema_version": 1,
        "source": "upstream-documentation",
        "capabilities": capabilities,
        "resolution": resolution,
    }
