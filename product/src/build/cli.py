
"""Build command-line interface, with a bounded cross-toolchain entry point."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import run_stage, selected_steps
from build.bootstrap.cross_chroot import prepare_stage
from build.bootstrap.distro_buildroot import run_diagnostic
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
    chroot.add_argument("--diagnose-native-binutils", action="store_true",
                       help="run an incomplete diagnostic build through native Binutils staging; never publish")
    native = commands.add_parser("distro-buildroot", help="Stage 1C initial native package production")
    native.add_argument("--root", type=Path, required=True, help="existing empty native buildroot workspace")
    native.add_argument("--cross-chroot", type=Path, required=True, help="verified Stage 1B tar.xz handoff")
    native.add_argument("--diagnose-native-sed", action="store_true",
                        help="run only native Sed construction/staging; always fail, never publish")
    args = parser.parse_args(argv)
    if args.operation == "distro-buildroot":
        if not args.diagnose_native_sed:
            print("FAIL distro-buildroot: Manage create/publish not implemented; "+
                  "refusing incomplete Stage 1C success", file=sys.stderr)
            return 1
        try:
            run_diagnostic(args.root, args.cross_chroot)
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"FAIL distro-buildroot: {exc}", file=sys.stderr)
            return 1
        return 1  # diagnostics must never declare Stage 1C completion
    if args.operation == "cross-chroot":
        if args.diagnose_native_binutils:
            print("[cross-chroot] DIAGNOSTIC: build may be lengthy and will exit unsuccessfully; no artifact publication", flush=True)
        else:
            print("[cross-chroot] Starting verified Stage 1B construction and Stage 1C handoff", flush=True)
        try:
            prepare_stage(args.root, args.cross_toolchain,
                          diagnose_native_binutils=args.diagnose_native_binutils)
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
