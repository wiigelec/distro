#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_REPOSITORY = Path.home() / "distro-g1-chroot" / "repository"
MANAGE_SCRIPT = ROOT / "product/src/proto/g1_chroot/manage.py"
INSTALL_SCRIPT = Path(__file__).resolve().with_name("install.py")


def run(argv: list[str], *, cwd: Path | None = None) -> None:
    print("+ " + " ".join(str(x) for x in argv), flush=True)
    subprocess.run([str(x) for x in argv], cwd=cwd, check=True)


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"required host command not found: {name}")


def kernel_from(root: Path) -> Path:
    kernels = sorted((root / "boot").glob("vmlinuz*"))
    if len(kernels) != 1:
        raise RuntimeError(
            "expected exactly one live kernel under /boot; found: "
            + ", ".join(path.name for path in kernels)
        )
    return kernels[0]


def write_init(root: Path) -> None:
    init = root / "init"
    init.write_text(
        "#!/bin/bash\n"
        "set -eu\n"
        "export PATH=/usr/bin:/bin:/usr/sbin:/sbin\n"
        "mkdir -p /dev /proc /sys /run /run/distro-media\n"
        "mountpoint -q /dev || mount -t devtmpfs devtmpfs /dev\n"
        "mountpoint -q /proc || mount -t proc proc /proc\n"
        "mountpoint -q /sys || mount -t sysfs sysfs /sys\n"
        "media=''\n"
        "for device in /dev/sr0 /dev/cdrom; do\n"
        "  if [ -b \"$device\" ] && mount -t iso9660 -o ro \"$device\" /run/distro-media; then\n"
        "    media=\"$device\"\n"
        "    break\n"
        "  fi\n"
        "done\n"
        "if [ -z \"$media\" ]; then\n"
        "  printf 'distro installer: unable to mount installation media\\n' >&2\n"
        "  exec setsid /bin/bash -i </dev/console >/dev/console 2>&1\n"
        "fi\n"
        "if [ ! -f /run/distro-media/distro/repository/database.json ]; then\n"
        "  printf 'distro installer: repository missing from installation media\\n' >&2\n"
        "  exec setsid /bin/bash -i </dev/console >/dev/console 2>&1\n"
        "fi\n"
        "printf '\\n'\n"
        "printf 'distro G2 installer prototype\\n'\n"
        "printf 'Run: distro-install /dev/vda --confirm-device /dev/vda --yes-really-destroy\\n'\n"
        "printf '\\n'\n"
        "exec setsid /bin/bash -i </dev/console >/dev/console 2>&1\n",
        encoding="utf-8",
    )
    init.chmod(0o755)


def embed_installer(root: Path) -> None:
    proto_dir = root / "usr/lib/distro/proto"
    proto_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MANAGE_SCRIPT, proto_dir / "manage.py")

    destination = root / "usr/bin/distro-install"
    shutil.copy2(INSTALL_SCRIPT, destination)
    destination.chmod(0o755)


def build_initramfs(root: Path, output: Path) -> None:
    command = (
        "set -euo pipefail; "
        "find . -print0 | "
        "cpio --null -o --format=newc --owner=0:0 2>/dev/null | "
        f"gzip -9 > {subprocess.list2cmdline([str(output)])}"
    )
    print("+ bash -c " + command, flush=True)
    subprocess.run(["bash", "-c", command], cwd=root, check=True)


def build_iso(repository: Path, output: Path) -> None:
    for command in ("grub-mkrescue", "xorriso", "cpio", "gzip", "find"):
        require_command(command)

    if not repository.joinpath("database.json").is_file():
        raise RuntimeError(f"repository database not found: {repository}")

    with tempfile.TemporaryDirectory(prefix="distro-g2-installer-") as temp:
        work = Path(temp)
        live_root = work / "root"
        iso_root = work / "iso"
        live_root.mkdir()
        iso_root.mkdir()

        run([
            str(ROOT / "product/scripts/manage"),
            "--repository",
            str(repository),
            "--root",
            str(live_root),
            "install",
            "g2-installer",
        ])

        embed_installer(live_root)
        write_init(live_root)

        media_repo = iso_root / "distro/repository"
        media_repo.parent.mkdir(parents=True)
        shutil.copytree(repository, media_repo)

        boot = iso_root / "boot"
        grub = boot / "grub"
        grub.mkdir(parents=True)
        shutil.copy2(kernel_from(live_root), boot / "vmlinuz")

        build_initramfs(live_root, boot / "initramfs.img")

        (grub / "grub.cfg").write_text(
            "set timeout=3\n"
            "set default=0\n"
            "\n"
            "menuentry 'distro G2 installer prototype' {\n"
            "    linux /boot/vmlinuz rdinit=/init console=tty0 console=ttyS0,115200n8\n"
            "    initrd /boot/initramfs.img\n"
            "}\n",
            encoding="utf-8",
        )

        output.parent.mkdir(parents=True, exist_ok=True)
        run(["grub-mkrescue", "-o", str(output), str(iso_root)])

    print(f"\nInstaller ISO: {output}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="build distro G2 BIOS installer ISO prototype")
    parser.add_argument("--repository", type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument("--output", type=Path, default=Path("/tmp/distro-g2-installer.iso"))
    args = parser.parse_args()
    build_iso(args.repository.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
