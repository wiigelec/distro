#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

IMAGE = "debian:13-slim"
PACKAGES = [
    "autoconf",
    "automake",
    "bash",
    "bison",
    "build-essential",
    "ca-certificates",
    "diffutils",
    "e2fsprogs",
    "expect",
    "findutils",
    "gawk",
    "gettext",
    "grep",
    "libcap-dev",
    "libgmp-dev",
    "libncurses-dev",
    "libpcre2-dev",
    "libreadline-dev",
    "libssl-dev",
    "make",
    "passwd",
    "patch",
    "sed",
    "tar",
    "texinfo",
    "util-linux",
    "wget",
    "xz-utils",
]


def container_backend() -> tuple[str, str]:
    for executable in ("podman", "docker"):
        path = shutil.which(executable)
        if path:
            return executable, path
    raise RuntimeError("fixture creation requires podman or docker on PATH")


def require_x86_64() -> None:
    machine = platform.machine().lower()
    if machine not in {"x86_64", "amd64"}:
        raise RuntimeError(
            f"execution fixture currently supports x86_64 only, got {machine}"
        )


def require_root() -> None:
    if os.geteuid() != 0:
        raise RuntimeError(
            "fixture extraction must run as root so ownership and permissions "
            "are preserved for chroot execution"
        )


def run_checked(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, text=True, **kwargs)


def create_fixture(output: Path) -> dict:
    require_root()
    require_x86_64()
    backend_name, backend = container_backend()

    output = output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    container_name = f"distro-lfs-optimize-{uuid.uuid4().hex[:12]}"
    package_line = " ".join(PACKAGES)
    setup = f"""
set -eux
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends {package_line}

cd /tmp
wget -q https://ftpmirror.gnu.org/readline/readline-8.3.tar.gz
tar -xzf readline-8.3.tar.gz
cd readline-8.3
sed -i '/MV.*old/d' Makefile.in
sed -i '/{{OLDSUFF}}/c:' support/shlib-install
sed -i 's/-Wl,-rpath,[^ ]*//' support/shobj-conf
sed -e '270a\\
     else\\
       chars_avail = 1;'      \\
    -e '288i\\   result = -1;' \\
    -i.orig input.c
./configure --prefix=/usr --disable-static --with-curses --docdir=/usr/share/doc/readline-8.3
make
make install
ldconfig
cd /
rm -rf /tmp/readline-8.3 /tmp/readline-8.3.tar.gz

useradd -m -s /bin/bash tester
mkdir -p /dev /proc /sys /run /tmp
chmod 1777 /tmp
rm -rf /var/lib/apt/lists/*
test -x /usr/bin/bash
test -x /usr/bin/gcc
test -x /usr/bin/make
test -x /usr/bin/sed
id tester
"""

    try:
        run_checked([
            backend, "run", "--name", container_name,
            IMAGE, "/bin/sh", "-c", setup,
        ])

        export = subprocess.Popen(
            [backend, "export", container_name],
            stdout=subprocess.PIPE,
        )
        if export.stdout is None:
            raise RuntimeError("container export did not provide stdout")
        extract = subprocess.run(
            ["tar", "-xpf", "-", "-C", str(output)],
            stdin=export.stdout,
        )
        export.stdout.close()
        export_status = export.wait()
        if export_status != 0:
            raise RuntimeError(
                f"{backend_name} export failed with exit code {export_status}"
            )
        if extract.returncode != 0:
            raise RuntimeError(
                f"fixture extraction failed with exit code {extract.returncode}"
            )
    finally:
        subprocess.run(
            [backend, "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    required = [
        "usr/bin/bash",
        "usr/bin/gcc",
        "usr/bin/make",
        "usr/bin/sed",
        "usr/bin/gawk",
        "usr/bin/patch",
        "usr/bin/autoconf",
        "usr/bin/automake",
        "usr/bin/bison",
        "usr/bin/expect",
        "etc/passwd",
    ]
    missing = [
        relative
        for relative in required
        if not os.path.lexists(output / relative)
    ]
    if missing:
        raise RuntimeError(f"fixture missing required paths: {missing}")

    symbol_check = subprocess.run(
        [
            "chroot",
            str(output),
            "/usr/bin/bash",
            "-lc",
            "nm -D /usr/lib/libreadline.so | grep -q ' rl_full_quoting_desired$'",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if symbol_check.returncode != 0:
        raise RuntimeError("fixture readline does not provide Bash 5.3 symbols")

    result = {
        "schema_version": 1,
        "status": "success",
        "kind": "execution-fixture",
        "image": IMAGE,
        "backend": backend_name,
        "root": str(output),
        "packages": PACKAGES,
        "limitations": [
            "This is a disposable execution harness, not an LFS release root.",
            "It proves executor mechanics before bootstrap/root construction exists.",
            "Milestone 2 equivalence still requires successful normalized package builds.",
        ],
    }
    (output / "fixture-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="create a disposable root for the LFS execution proof"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/lfs-optimize-fixture"),
    )
    args = parser.parse_args()

    result = create_fixture(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
