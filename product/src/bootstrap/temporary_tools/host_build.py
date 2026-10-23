"""FS-001 M2 Part 1 host cross-build: construct Generation A."""
import argparse
import urllib.request
import urllib.error
import os
from pathlib import Path
from package_runner import main as build_temporary_tools


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--cross-toolchain', required=True, type=Path)
    args = parser.parse_args(argv)
    root = args.root.expanduser().absolute()
    if root.name != 'root' or root.is_symlink():
        parser.error('--root must identify the /root target directory, not the project')
    if os.geteuid() == 0:
        parser.error('host cross-build must run unprivileged')
    return build_temporary_tools(root.parent, args.cross_toolchain)


if __name__ == '__main__':
    raise SystemExit(main())
