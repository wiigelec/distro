#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_REPOSITORY = Path("/run/distro-media/distro/repository")
DEFAULT_TARGET = Path("/mnt/distro-target")
MANAGE = Path("/usr/lib/distro/proto/manage.py")
PACKAGE = "g2-installer"


def run(argv: list[str], *, input_text: str | None = None, capture: bool = False) -> str:
    print("+ " + " ".join(argv), flush=True)
    proc = subprocess.run(
        argv,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(argv)}")
    return proc.stdout.strip() if capture and proc.stdout is not None else ""


def require_root() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("installer must run as root")


def require_block_device(device: Path) -> None:
    try:
        mode = device.stat().st_mode
    except FileNotFoundError as exc:
        raise RuntimeError(f"target device does not exist: {device}") from exc
    if not stat.S_ISBLK(mode):
        raise RuntimeError(f"target is not a block device: {device}")


def reject_mounted_device(device: Path) -> None:
    prefix = str(device)
    conflicts = []
    for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if fields and (fields[0] == prefix or fields[0].startswith(prefix)):
            conflicts.append(line)
    if conflicts:
        raise RuntimeError(
            "target device or one of its partitions is mounted:\n"
            + "\n".join(conflicts)
        )


def partition_path(device: Path) -> Path:
    text = str(device)
    return Path(text + ("p1" if text[-1].isdigit() else "1"))


def wait_for_partition(path: Path) -> None:
    for _ in range(50):
        if path.exists():
            return
        time.sleep(0.1)
    raise RuntimeError(f"partition device did not appear: {path}")


def find_kernel(target: Path) -> str:
    kernels = sorted((target / "boot").glob("vmlinuz*"))
    if len(kernels) != 1:
        raise RuntimeError(
            "expected exactly one installed kernel under /boot; found: "
            + ", ".join(path.name for path in kernels)
        )
    return kernels[0].name


def install(device: Path, repository: Path, target: Path) -> None:
    require_root()
    require_block_device(device)
    reject_mounted_device(device)

    if not repository.joinpath("database.json").is_file():
        raise RuntimeError(f"prototype repository is incomplete or missing: {repository}")
    if not MANAGE.is_file():
        raise RuntimeError(f"Manage prototype is missing: {MANAGE}")

    part = partition_path(device)

    table = "label: dos\nunit: sectors\n\nstart=2048, type=83, bootable\n"
    run(["sfdisk", "--wipe", "always", str(device)], input_text=table)
    run(["blockdev", "--rereadpt", str(device)])
    wait_for_partition(part)
    run(["mkfs.ext4", "-F", "-L", "distro-root", str(part)])

    target.mkdir(parents=True, exist_ok=True)
    run(["mount", str(part), str(target)])
    try:
        run([
            sys.executable,
            str(MANAGE),
            "--repository",
            str(repository),
            "--root",
            str(target),
            "install",
            PACKAGE,
        ])

        uuid = run(["blkid", "-s", "UUID", "-o", "value", str(part)], capture=True)
        if not uuid:
            raise RuntimeError(f"could not determine filesystem UUID: {part}")

        etc = target / "etc"
        etc.mkdir(parents=True, exist_ok=True)
        (etc / "fstab").write_text(
            f"UUID={uuid} / ext4 defaults 0 1\n",
            encoding="utf-8",
        )

        run([
            "grub-install",
            "--target=i386-pc",
            f"--boot-directory={target / 'boot'}",
            str(device),
        ])

        kernel = find_kernel(target)
        grub = target / "boot/grub"
        grub.mkdir(parents=True, exist_ok=True)
        (grub / "grub.cfg").write_text(
            "set timeout=3\n"
            "set default=0\n"
            "\n"
            "menuentry 'distro G2 prototype' {\n"
            f"    search --no-floppy --fs-uuid --set=root {uuid}\n"
            f"    linux /boot/{kernel} root=UUID={uuid} rw "
            "console=tty0 console=ttyS0,115200n8\n"
            "}\n",
            encoding="utf-8",
        )
        run(["sync"])
    finally:
        run(["umount", str(target)])

    print(f"\nG2 prototype installation complete. Boot from {device}.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="distro G2 destructive BIOS installer prototype")
    parser.add_argument("device", type=Path)
    parser.add_argument("--repository", type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--confirm-device", required=True)
    parser.add_argument("--yes-really-destroy", action="store_true")
    args = parser.parse_args()

    if not args.yes_really_destroy:
        parser.error("--yes-really-destroy is required")
    if args.confirm_device != str(args.device):
        parser.error("--confirm-device must exactly match the target device")

    install(args.device, args.repository, args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
