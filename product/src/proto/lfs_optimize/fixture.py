#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bootstrap import build_fixture


def main() -> int:
    parser = argparse.ArgumentParser(
        description="create the LFS Chapter 5-7 chroot handoff fixture"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/lfs-optimize-fixture"),
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("/tmp/lfs-optimize-cache"),
    )
    parser.add_argument("--builder-user")
    args = parser.parse_args()

    result = build_fixture(args.output, args.cache, args.builder_user)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
