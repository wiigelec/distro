#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_manifest(name: str) -> dict:
    path = HERE / f"{name}.json"
    if not path.is_file():
        raise RuntimeError(f"unknown build manifest: {name}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise RuntimeError(f"unsupported manifest schema: {path}")
    if manifest.get("name") != name:
        raise RuntimeError(f"manifest identity mismatch: {path}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="G1 chroot Build prototype")
    parser.add_argument("manifest")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)

    print(json.dumps({
        "status": "prototype",
        "operation": "build",
        "manifest": manifest["name"],
        "packages": manifest["packages"],
        "next": "version and recipe discovery not implemented yet"
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
