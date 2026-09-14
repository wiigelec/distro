#!/usr/bin/env python3
"""Install v0: create a bootable prototype system image."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

REQUIRED_TOOLS = ("sfdisk", "losetup", "mkfs.ext4", "mount", "umount", "extlinux")


def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def require_root():
    if os.geteuid() != 0:
        raise RuntimeError("Install v0 must run as root")


def require_tools():
    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        raise RuntimeError("missing installer tools: " + ", ".join(sorted(missing)))


def find_mbr():
    for path in (
        Path("/usr/lib/syslinux/bios/mbr.bin"),
        Path("/usr/lib/syslinux/mbr/mbr.bin"),
        Path("/usr/lib/SYSLINUX/mbr.bin"),
        Path("/usr/lib/EXTLINUX/mbr.bin"),
    ):
        if path.exists():
            return path
    raise RuntimeError("unable to locate Syslinux MBR boot code; install the host Syslinux package")


def partition_path(loop_device):
    path = Path(f"{loop_device}p1")
    for _ in range(50):
        if path.exists():
            return path
        time.sleep(0.1)
    raise RuntimeError(f"partition device did not appear: {path}")


def manage_path():
    return Path(__file__).resolve().parents[1] / "manager" / "manage.py"


def install(repository, image, size_mib):
    require_root()
    require_tools()
    repository = repository.resolve()
    image = image.resolve()
    image.parent.mkdir(parents=True, exist_ok=True)
    if image.exists():
        image.unlink()

    with image.open("wb") as handle:
        handle.truncate(size_mib * 1024 * 1024)

    run(["sfdisk", "--wipe", "always", str(image)], input="label: dos\n,,83,*\n", text=True)

    loop_device = subprocess.check_output(
        ["losetup", "--find", "--show", "--partscan", str(image)], text=True
    ).strip()
    if not loop_device:
        raise RuntimeError("losetup did not return a loop device")

    mounted = False
    with tempfile.TemporaryDirectory(prefix="distro-install-") as temporary:
        root = Path(temporary) / "root"
        root.mkdir()
        try:
            partition = partition_path(loop_device)
            run([
                "mkfs.ext4", "-F", "-L", "distro-root",
                "-O", "^64bit,^metadata_csum", str(partition),
            ])
            run(["mount", str(partition), str(root)])
            mounted = True

            python = shutil.which("python3") or "/usr/bin/python3"
            run([
                python, str(manage_path()), "install",
                "--repository", str(repository),
                "--root", str(root),
                "system",
            ])

            bootloader_dir = root / "boot/extlinux"
            bootloader_dir.mkdir(parents=True, exist_ok=True)
            (bootloader_dir / "extlinux.conf").write_text(
                "DEFAULT distro\n"
                "PROMPT 0\n"
                "TIMEOUT 10\n"
                "\n"
                "LABEL distro\n"
                "  LINUX /boot/vmlinuz\n"
                "  INITRD /boot/initrd.img\n"
                "  APPEND root=/dev/vda1 rw init=/sbin/init console=ttyS0\n"
            )
            run(["extlinux", "--install", str(bootloader_dir)])

            with find_mbr().open("rb") as source, image.open("r+b") as target:
                target.seek(0)
                target.write(source.read(440))
                target.flush()
                os.fsync(target.fileno())
            run(["sync"])
        finally:
            if mounted:
                subprocess.run(["umount", str(root)], check=False)
            subprocess.run(["losetup", "--detach", loop_device], check=False)

    return {
        "schema_version": 1,
        "status": "success",
        "image": str(image),
        "size_mib": size_mib,
        "partition_table": "dos",
        "root_filesystem": "ext4",
        "bootloader": "extlinux",
        "profile": "system",
    }


def main():
    parser = argparse.ArgumentParser(description="Install v0 prototype")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--size-mib", type=int, default=1024)
    args = parser.parse_args()
    if args.size_mib < 512:
        raise RuntimeError("--size-mib must be at least 512")
    print(json.dumps(install(args.repository, args.image, args.size_mib), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
