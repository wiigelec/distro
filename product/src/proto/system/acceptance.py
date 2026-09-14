#!/usr/bin/env python3
"""Check a Manage v0 root before the chroot smoke test."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/tmp/distro-root"))
    args = parser.parse_args()

    root = args.root.resolve()
    database_path = root / "var/lib/distro/manage/installed.json"
    database = json.loads(database_path.read_text())

    records = {
        record["identity"]["name"]: record
        for record in database["packages"]
    }

    if set(records) != {"musl", "busybox"}:
        raise RuntimeError(
            f"expected musl and busybox installed, found {sorted(records)}"
        )
    if records["musl"]["install_reason"] != "dependency":
        raise RuntimeError("musl should be installed as a dependency")
    if records["busybox"]["install_reason"] != "explicit":
        raise RuntimeError("busybox should be installed explicitly")

    required = [
        root / "lib/ld-musl-x86_64.so.1",
        root / "usr/lib/libc.so",
        root / "bin/busybox",
        root / "bin/sh",
        root / "bin/ls",
    ]
    missing = [
        str(path)
        for path in required
        if not (path.exists() or path.is_symlink())
    ]
    if missing:
        raise RuntimeError(f"root is missing required paths: {missing}")

    if not os.access(root / "bin/busybox", os.X_OK):
        raise RuntimeError("/bin/busybox is not executable")

    print(json.dumps({
        "schema_version": 1,
        "status": "success",
        "root": str(root),
        "installed": {
            name: {
                "identity": record["identity"],
                "install_reason": record["install_reason"],
            }
            for name, record in sorted(records.items())
        },
        "required_paths": [
            str(path.relative_to(root))
            for path in required
        ],
        "next": f"sudo chroot {root} /bin/sh",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
