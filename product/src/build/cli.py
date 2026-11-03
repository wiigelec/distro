
"""Build command-line interface, with a bounded cross-toolchain entry point."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import run_stage, selected_steps
from build.bootstrap.cross_chroot import prepare_stage
from build.host_requirements import qualify_host
from build.host_sandbox import probe_bubblewrap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build")
    commands = parser.add_subparsers(dest="operation", required=True)
    cross = commands.add_parser("cross-toolchain", help="construct the initial cross-toolchain")
    cross.add_argument("--root", type=Path, help="existing, empty cross-toolchain workspace")
    cross.add_argument("--check-host", action="store_true",
                       help="validate selections, host and sandbox without changing workspace")
    chroot = commands.add_parser("cross-chroot", help="prepare verified cross-chroot input and selection")
    chroot.add_argument("--root", type=Path, required=True, help="existing, empty cross-chroot workspace")
    chroot.add_argument("--cross-toolchain", type=Path, required=True, help="verified cross-toolchain tar.xz handoff")
    args = parser.parse_args(argv)
    if args.operation == "cross-chroot":
        print("[cross-chroot] Starting cross-chroot preparation", flush=True)
        try:
            prepare_stage(args.root, args.cross_toolchain)
            return 0
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"FAIL cross-chroot: {exc}", file=sys.stderr)
            return 1
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
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL cross-toolchain: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
