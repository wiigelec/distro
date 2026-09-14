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
    print(json.dumps(verified, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
