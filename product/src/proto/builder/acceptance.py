#!/usr/bin/env python3
"""Acceptance check for a completed curl end-to-end prototype build."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from verify import verify_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "result",
        nargs="?",
        type=Path,
        default=Path("/tmp/distro-builder/curl/result.json"),
    )
    args = parser.parse_args()

    verified = verify_result(args.result)

    result = json.loads(args.result.read_text())
    environment = result.get("environment", {})
    if environment.get("dependency_source") != "upstream-documentation":
        raise RuntimeError("curl fixture expected documentation-derived dependencies")

    capability_names = {
        item["name"]
        for item in environment.get("capabilities", [])
    }
    expected_capabilities = {
        "tls.openssl",
        "compression.zlib",
        "cookies.libpsl",
        "compression.brotli",
        "compression.zstd",
        "http2.nghttp2",
        "idn.libidn2",
        "ssh.libssh2",
    }
    missing = expected_capabilities - capability_names
    if missing:
        raise RuntimeError(
            f"curl fixture is missing discovered capabilities: {sorted(missing)}"
        )

    resolver = environment.get("resolver", {})
    if resolver.get("distribution") != "debian":
        raise RuntimeError("curl fixture expected Debian dependency resolution")
    print(json.dumps(verified, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
