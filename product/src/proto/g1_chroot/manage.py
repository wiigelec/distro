#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser(description="G1 chroot Manage prototype")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install")
    install.add_argument("package")

    args = parser.parse_args()

    if args.command == "install":
        print(json.dumps({
            "status": "prototype",
            "operation": "install",
            "package": args.package,
            "next": "repository resolution and installation not implemented yet"
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
