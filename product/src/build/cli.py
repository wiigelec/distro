
"""Build command-line interface, with a bounded cross-toolchain entry point."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import run_stage, selected_steps
from build.host_requirements import qualify_host
from build.host_sandbox import probe_bubblewrap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build")
    commands = parser.add_subparsers(dest="operation", required=True)
    cross = commands.add_parser("cross-toolchain", help="construct the initial cross-toolchain")
    cross.add_argument("--root", type=Path, help="existing, empty Stage 1A workspace")
    cross.add_argument("--check-host", action="store_true",
                       help="validate selections, host and sandbox without changing workspace")
    args = parser.parse_args(argv)
    if args.operation != "cross-toolchain":
        parser.error("unsupported operation")
    if not args.check_host and args.root is None:
        cross.error("--root is required for construction")
    try:
        if args.check_host:
            if sys.platform != "linux":
                raise RuntimeError("Cross-toolchain construction requires a Linux host")
            selected_steps()
            qualify_host()
            probe_bubblewrap()
            print("Cross-toolchain host preflight: PASS")
            return 0
        run_stage(args.root)
        # Never claim successful construction until archive publication is implemented.
        raise RuntimeError("cross-toolchain returned without a published artifact")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL cross-toolchain: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
