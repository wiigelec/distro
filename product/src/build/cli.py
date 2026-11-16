
"""Build command-line interface, with a bounded cross-toolchain entry point."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from build.bootstrap.cross_toolchain import run_stage, selected_steps
from build.bootstrap.cross_chroot import prepare_stage
from build.bootstrap.distro_buildroot import run_diagnostic, run_stage as run_native_stage
from build.native_bootstrap_prefix import run_bootstrap_prefix
from build.native_glibc_transition import run_glibc_transition
from build.native_binutils_transition import run_binutils_transition
from build.native_gcc_transition import run_gcc_transition
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
    prefix = commands.add_parser('distro-buildroot-prefix',
                                 help='build only authenticated FS-004 filesystem and Linux headers')
    prefix.add_argument('--root', type=Path, required=True,
                        help='existing, empty construction workspace')
    prefix.add_argument('--cross-chroot', type=Path, required=True,
                        help='verified Stage 1B handoff archive')
    prefix.add_argument('--source-repo', type=Path, required=True,
                        help='selected source repository root')
    prefix.add_argument('--revision', required=True,
                        help='immutable source repository Git revision')
    glibc = commands.add_parser('distro-buildroot-glibc',
                                help='build Glibc using verified Stage 1B and Manage-installed Linux headers')
    glibc.add_argument('--root', required=True, type=Path)
    glibc.add_argument('--cross-chroot', required=True, type=Path)
    glibc.add_argument('--source-repo', required=True, type=Path)
    glibc.add_argument('--revision', required=True)
    glibc.add_argument('--prerequisite-repo', required=True, type=Path)
    glibc.add_argument('--prerequisite-root', required=True, type=Path)
    binutils = commands.add_parser(
        'distro-buildroot-binutils',
        help='bootstrap native Binutils with Stage 1B tools and Manage-installed Glibc seed')
    binutils.add_argument('--root', required=True, type=Path)
    binutils.add_argument('--cross-chroot', required=True, type=Path)
    binutils.add_argument('--source-repo', required=True, type=Path)
    binutils.add_argument('--revision', required=True)
    binutils.add_argument('--seed-repo', required=True, type=Path)
    binutils.add_argument('--seed-root', required=True, type=Path)
    gcc = commands.add_parser(
        'distro-buildroot-gcc',
        help='build native GCC 16.2.0 with authenticated Manage-installed linker seed')
    gcc.add_argument('--root', required=True, type=Path)
    gcc.add_argument('--cross-chroot', required=True, type=Path)
    gcc.add_argument('--source-repo', required=True, type=Path)
    gcc.add_argument('--revision', required=True)
    gcc.add_argument('--linker-repo', required=True, type=Path)
    gcc.add_argument('--linker-root', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.operation == 'distro-buildroot-gcc':
        try:
            run_gcc_transition(
                args.root, args.cross_chroot,
                source_repository=args.source_repo, revision=args.revision,
                linker_repository=args.linker_repo,
                installed_linker=args.linker_root)
            return 0
        except (OSError, RuntimeError, ValueError) as exc:
            print(f'FAIL distro-buildroot-gcc: {exc}', file=sys.stderr)
            return 1
    if args.operation == 'distro-buildroot-binutils':
        try:
            run_binutils_transition(
                args.root, args.cross_chroot,
                source_repository=args.source_repo, revision=args.revision,
                seed_repository=args.seed_repo, installed_seed=args.seed_root)
            return 0
        except (OSError, RuntimeError, ValueError) as exc:
            print(f'FAIL distro-buildroot-binutils: {exc}', file=sys.stderr)
            return 1
    if args.operation == 'distro-buildroot-glibc':
        try:
            run_glibc_transition(args.root, args.cross_chroot,
                                 source_repository=args.source_repo, revision=args.revision,
                                 prerequisite_repository=args.prerequisite_repo,
                                 installed_prerequisites=args.prerequisite_root)
            return 0
        except (OSError, RuntimeError, ValueError) as exc:
            print(f'FAIL distro-buildroot-glibc: {exc}', file=sys.stderr)
            return 1
    if args.operation == 'distro-buildroot-prefix':
        try:
            run_bootstrap_prefix(args.root, args.cross_chroot,
                                 source_repository=args.source_repo,
                                 revision=args.revision)
            return 0
        except (OSError, RuntimeError, ValueError) as exc:
            print(f'FAIL distro-buildroot-prefix: {exc}', file=sys.stderr)
            return 1
    if args.operation == "distro-buildroot":
        try:
            if args.diagnose_native_sed:
                run_diagnostic(args.root, args.cross_chroot)
                return 1  # diagnostic never reports accepted completion
            run_native_stage(args.root, args.cross_chroot)
            return 0
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"FAIL distro-buildroot: {exc}", file=sys.stderr)
            return 1
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
