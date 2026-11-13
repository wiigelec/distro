"""Manage's initial package creation and verification command line."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from manage.package import PackageError, create, verify
from manage.repository import publish, verify_repository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manage")
    commands = parser.add_subparsers(dest="operation", required=True)
    make = commands.add_parser("create", help="create a package from Build staging")
    make.add_argument("--package", required=True)
    make.add_argument("--build", required=True, type=Path)
    check = commands.add_parser("verify", help="independently verify a package archive")
    check.add_argument("--artifact", required=True, type=Path)
    pub = commands.add_parser("publish", help="publish a created package to a local repository")
    pub.add_argument("--package", required=True)
    pub.add_argument("--repo", required=True, type=Path)
    pub.add_argument("--build", required=True, type=Path, help="Build-to-Manage exchange directory")
    repo_check = commands.add_parser("verify-repo", help="independently verify a local repository")
    repo_check.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.operation == "create":
            artifact = create(args.package, args.build)
            print(f"[manage] Created and verified {artifact}", flush=True)
        elif args.operation == "publish":
            artifact = publish(args.package, args.repo, args.build)
            print(f"[manage] Published {artifact}", flush=True)
        elif args.operation == "verify-repo":
            index = verify_repository(args.repo)
            print(f"[manage] Verified {len(index['packages'])} repository package(s)", flush=True)
        else:
            metadata = verify(args.artifact)
            ident = metadata["identity"]
            print(f"[manage] Verified {ident['name']} {ident['version']} {ident['architecture']} r{ident['revision']}", flush=True)
        return 0
    except (PackageError, OSError, ValueError) as exc:
        print(f"FAIL manage: {exc}", file=sys.stderr)
        return 1
