#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from artifact import snapshot, snapshot_digest
from execute import cached_download, clone_root, effective_jobs, safe_extract_source, virtual_mounts
from resolve import HERE, load_json

PLAN_PATH = HERE / "boot-13.1.json"


def require_root() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("boot proof requires root for chroot, loop mount, and filesystem image creation")


def require_x86_64() -> None:
    machine = platform.machine().lower()
    if machine not in {"x86_64", "amd64"}:
        raise RuntimeError(f"boot proof currently supports x86_64 only, got {machine}")


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"boot proof requires host tool: {name}")
    return path


def run(argv: list[str], *, cwd: Path | None = None, stdout=None, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        cwd=cwd,
        stdout=stdout,
        stderr=subprocess.STDOUT if stdout is not None else None,
        text=True,
        check=True,
        timeout=timeout,
    )


def boot_plan() -> dict[str, Any]:
    definition = load_json(PLAN_PATH)
    kernel = definition["kernel"]
    return {
        "schema_version": 1,
        "status": "success",
        "mode": "plan",
        "name": definition["name"],
        "basis": definition["basis"],
        "kernel": {
            "version": kernel["version"],
            "source": kernel["source"],
            "required_builtin": kernel["required_builtin"],
        },
        "qemu": definition["qemu"],
        "proof": definition["proof"],
        "authority": definition["authority"],
    }


def chroot_shell(root: Path, command: str, log, jobs: int) -> None:
    argv = [
        "chroot", str(root.resolve()), "/usr/bin/env", "-i",
        "HOME=/root", "PATH=/usr/bin:/usr/sbin", f"MAKEFLAGS=-j{jobs}",
        "/bin/bash", "-o", "pipefail", "-c", command,
    ]
    run(argv, stdout=log)


def configure_kernel(source_dir: str, required: list[str]) -> str:
    enables = "\n".join(f"scripts/config --enable {symbol}" for symbol in required)
    checks = "\n".join(f"grep -qx 'CONFIG_{symbol}=y' .config" for symbol in required)
    return f"""cd {source_dir}
make mrproper
make defconfig
{enables}
make olddefconfig
{checks}
make
make modules_install
"""


def install_boot_harness(root: Path, definition: dict[str, Any]) -> None:
    root_device = definition["qemu"]["root_device"]
    console = definition["qemu"]["console"]
    marker = definition["proof"]["marker"]
    unit = definition["proof"]["unit"]

    etc = root / "etc"
    etc.mkdir(parents=True, exist_ok=True)
    (etc / "fstab").write_text(
        "# distro LFS QEMU boot-proof filesystem table\n"
        f"{root_device} / ext4 defaults 1 1\n",
        encoding="utf-8",
    )
    (etc / "hostname").write_text("lfs-qemu\n", encoding="utf-8")
    (etc / "hosts").write_text(
        "127.0.0.1 localhost lfs-qemu\n"
        "::1 localhost ip6-localhost ip6-loopback\n",
        encoding="utf-8",
    )

    unit_dir = etc / "systemd/system"
    wants = unit_dir / "multi-user.target.wants"
    wants.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / unit
    unit_path.write_text(
        "[Unit]\n"
        "Description=Distro booted-LFS proof marker\n"
        "After=systemd-user-sessions.service\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart=/bin/sh -c 'pid1=$(cat /proc/1/comm); test \"$pid1\" = systemd; "
        f"printf \"{marker} kernel=%s pid1=%s\\\\n\" \"$(uname -r)\" \"$pid1\" > /dev/{console}'\n"
        "ExecStart=/usr/bin/systemctl --no-block poweroff\n"
        "RemainAfterExit=yes\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n",
        encoding="utf-8",
    )
    link = wants / unit
    link.unlink(missing_ok=True)
    link.symlink_to(f"/etc/systemd/system/{unit}")


def image_size_bytes(root: Path) -> int:
    completed = subprocess.run(
        ["du", "-s", "-B1", str(root)],
        check=True, capture_output=True, text=True,
    )
    used = int(completed.stdout.split()[0])
    gib = 1024 ** 3
    desired = max(6 * gib, int(used * 1.35) + gib)
    return math.ceil(desired / gib) * gib


def create_root_image(root: Path, image: Path, mountpoint: Path) -> int:
    size = image_size_bytes(root)
    image.parent.mkdir(parents=True, exist_ok=True)
    mountpoint.mkdir(parents=True, exist_ok=True)
    image.unlink(missing_ok=True)

    run(["truncate", "-s", str(size), str(image)])
    run(["mkfs.ext4", "-F", "-L", "LFSROOT", str(image)])
    mounted = False
    try:
        run(["mount", "-o", "loop", str(image), str(mountpoint)])
        mounted = True
        run(["cp", "-a", "--one-file-system", f"{root.resolve()}/.", str(mountpoint.resolve())])
        run(["sync"])
    finally:
        if mounted:
            subprocess.run(["umount", str(mountpoint)], check=False)
    return size


def qemu_argv(definition: dict[str, Any], kernel: Path, image: Path) -> list[str]:
    qemu = definition["qemu"]
    accel = "kvm" if Path("/dev/kvm").exists() and os.access("/dev/kvm", os.R_OK | os.W_OK) else "tcg"
    cpu = "host" if accel == "kvm" else "max"
    append = (
        f"root={qemu['root_device']} rw "
        f"console={qemu['console']},115200n8 "
        f"systemd.unit={definition['proof']['target']}"
    )
    return [
        "qemu-system-x86_64",
        "-accel", accel,
        "-cpu", cpu,
        "-m", str(qemu["memory_mib"]),
        "-smp", str(qemu["cpus"]),
        "-nographic",
        "-no-reboot",
        "-kernel", str(kernel),
        "-append", append,
        "-drive", f"file={image},format=raw,if=virtio",
        "-netdev", "user,id=net0",
        "-device", "virtio-net-pci,netdev=net0",
    ]


def build_boot_proof(root: Path, work: Path, cache: Path, timeout: int | None = None) -> dict[str, Any]:
    require_root()
    require_x86_64()
    for tool in ("qemu-system-x86_64", "mkfs.ext4", "mount", "umount", "truncate", "du"):
        require_tool(tool)

    root = root.resolve()
    if not (root / "usr/bin/bash").is_file():
        raise RuntimeError(f"{root}: completed LFS root lacks /usr/bin/bash")
    if not (root / "usr/lib/systemd/systemd").is_file():
        raise RuntimeError(f"{root}: completed LFS root lacks systemd PID 1")

    definition = load_json(PLAN_PATH)
    boot_work = work / "boot"
    boot_root = boot_work / "root"
    mountpoint = boot_work / "mnt"
    image = boot_work / "lfs-root.ext4"
    kernel_out = boot_work / f"vmlinuz-{definition['kernel']['version']}"
    log_path = boot_work / "kernel-build.log"
    console_path = boot_work / "qemu-console.log"
    result_path = boot_work / "result.json"
    boot_work.mkdir(parents=True, exist_ok=True)

    clone_root(root, boot_root)
    input_digest = snapshot_digest(snapshot(boot_root))
    install_boot_harness(boot_root, definition)

    archive = cached_download(definition["kernel"]["source"], cache, mirror_required=False)
    unpack = boot_root / "tmp/distro-boot-kernel-unpack"
    if unpack.exists():
        shutil.rmtree(unpack)
    source = safe_extract_source(archive, unpack)
    source_dir = "/tmp/distro-boot-linux"
    host_source = boot_root / source_dir.lstrip("/")
    if host_source.exists():
        shutil.rmtree(host_source)
    source.rename(host_source)
    shutil.rmtree(unpack)

    jobs = effective_jobs()
    with log_path.open("w", encoding="utf-8") as log:
        with virtual_mounts(boot_root):
            chroot_shell(
                boot_root,
                configure_kernel(source_dir, definition["kernel"]["required_builtin"]),
                log,
                jobs,
            )

    built_kernel = host_source / "arch/x86/boot/bzImage"
    if not built_kernel.is_file():
        raise RuntimeError("kernel build did not produce arch/x86/boot/bzImage")
    shutil.copy2(built_kernel, kernel_out)
    shutil.rmtree(host_source)

    size = create_root_image(boot_root, image, mountpoint)
    argv = qemu_argv(definition, kernel_out, image)
    effective_timeout = timeout or int(definition["qemu"]["timeout_seconds"])

    timed_out = False
    try:
        completed = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=effective_timeout,
        )
        console = completed.stdout or ""
        qemu_exit = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        raw = exc.stdout or ""
        console = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
        qemu_exit = None

    console_path.write_text(console, encoding="utf-8")
    marker = definition["proof"]["marker"]
    marker_seen = marker in console
    result = {
        "schema_version": 1,
        "status": "success" if marker_seen else "failure",
        "kind": "booted-lfs-qemu-proof",
        "basis": definition["basis"],
        "input_root": str(root),
        "input_root_sha256": input_digest,
        "boot_root": str(boot_root),
        "kernel": str(kernel_out),
        "kernel_version": definition["kernel"]["version"],
        "root_image": str(image),
        "root_image_bytes": size,
        "qemu_command": argv,
        "qemu_exit_code": qemu_exit,
        "qemu_timed_out": timed_out,
        "console_log": str(console_path),
        "proof_marker": marker,
        "proof_marker_seen": marker_seen,
        "expected_pid1": definition["proof"]["expected_pid1"],
    }
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="build a kernel and prove the completed LFS root boots under QEMU")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/lfs-optimize-boot"))
    parser.add_argument("--cache", type=Path, default=Path("/tmp/lfs-optimize-cache"))
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()

    if args.plan:
        result = boot_plan()
    else:
        if args.root is None:
            parser.error("--root is required unless --plan is used")
        result = build_boot_proof(args.root, args.work, args.cache, args.timeout)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
