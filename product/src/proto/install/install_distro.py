#!/usr/bin/env python3
"""Install the prototype distro from the booted installer environment."""

from __future__ import annotations
import argparse, json, os, shutil, stat, subprocess, tempfile, time
from pathlib import Path

DEFAULT_REPOSITORY = Path("/opt/distro/repository")
DEFAULT_MANAGER = Path("/opt/distro/manage.py")
REQUIRED_TOOLS = ("sfdisk","blockdev","udevadm","mkfs.ext4","mount","umount","extlinux")

def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)

def require_root():
    if os.geteuid() != 0:
        raise RuntimeError("install-distro must run as root")

def require_tools():
    missing=[n for n in REQUIRED_TOOLS if shutil.which(n) is None]
    if missing:
        raise RuntimeError("installer environment is missing required tools: "+", ".join(sorted(missing)))

def require_block_device(path):
    path=path.resolve()
    try:
        mode=path.stat().st_mode
    except FileNotFoundError as e:
        raise RuntimeError(f"target device does not exist: {path}") from e
    if not stat.S_ISBLK(mode):
        raise RuntimeError(f"target is not a block device: {path}")
    return path

def mounted_paths(device):
    r=subprocess.run(["lsblk","-nrpo","NAME,MOUNTPOINTS",str(device)],check=True,stdout=subprocess.PIPE,text=True)
    out=[]
    for line in r.stdout.splitlines():
        fields=line.split(None,1)
        if len(fields)==2 and fields[1].strip():
            out.append((fields[0],fields[1].strip()))
    return out

def partition_path(device):
    suffix="p1" if device.name[-1:].isdigit() else "1"
    return Path(str(device)+suffix)

def wait_for_partition(path):
    for _ in range(100):
        if path.exists():
            return
        time.sleep(0.1)
    raise RuntimeError(f"partition device did not appear: {path}")

def find_mbr():
    for path in (
        Path("/usr/lib/syslinux/bios/mbr.bin"),
        Path("/usr/lib/syslinux/mbr/mbr.bin"),
        Path("/usr/lib/SYSLINUX/mbr.bin"),
        Path("/usr/lib/EXTLINUX/mbr.bin"),
    ):
        if path.exists():
            return path
    raise RuntimeError("installer environment has no Syslinux MBR boot code")

def install(repository, manager, target):
    require_root(); require_tools()
    repository=repository.resolve(); manager=manager.resolve(); target=require_block_device(target)
    if not (repository/"database.json").is_file():
        raise RuntimeError(f"invalid package repository: {repository}")
    if not manager.is_file():
        raise RuntimeError(f"Manage implementation not found: {manager}")
    mounted=mounted_paths(target)
    if mounted:
        rendered=", ".join(f"{n} at {m}" for n,m in mounted)
        raise RuntimeError(f"refusing to overwrite mounted target: {rendered}")

    print(f"install-distro: replacing partition table on {target}", flush=True)
    run(["sfdisk","--wipe","always",str(target)],input="label: dos\n,,83,*\n",text=True)
    run(["blockdev","--rereadpt",str(target)])
    run(["udevadm","settle"])
    partition=partition_path(target); wait_for_partition(partition)

    print(f"install-distro: creating ext4 on {partition}", flush=True)
    run(["mkfs.ext4","-F","-L","distro-root","-O","^64bit,^metadata_csum",str(partition)])

    with tempfile.TemporaryDirectory(prefix="distro-target-") as td:
        root=Path(td); mounted_target=False
        try:
            run(["mount",str(partition),str(root)]); mounted_target=True
            print("install-distro: installing system through Manage", flush=True)
            python=shutil.which("python3") or "/usr/bin/python3"
            run([python,str(manager),"install","--repository",str(repository),"--root",str(root),"system"])
            boot=root/"boot/extlinux"; boot.mkdir(parents=True,exist_ok=True)
            (boot/"extlinux.conf").write_text(
                "DEFAULT distro\nPROMPT 0\nTIMEOUT 10\n\n"
                "LABEL distro\n  LINUX /boot/vmlinuz\n  INITRD /boot/initrd.img\n"
                "  APPEND root=LABEL=distro-root rw init=/sbin/init console=ttyS0\n"
            )
            print("install-distro: installing EXTLINUX", flush=True)
            run(["extlinux","--install",str(boot)])
            with find_mbr().open("rb") as source, target.open("r+b") as disk:
                disk.seek(0); disk.write(source.read(440)); disk.flush(); os.fsync(disk.fileno())
            run(["sync"])
        finally:
            if mounted_target:
                subprocess.run(["umount",str(root)],check=False)

    return {"schema_version":1,"status":"success","target":str(target),"partition":str(partition),
            "partition_table":"dos","root_filesystem":"ext4","root_label":"distro-root",
            "bootloader":"extlinux","profile":"system"}

def main():
    p=argparse.ArgumentParser(prog="install-distro",description="Install the prototype distro onto a block device")
    p.add_argument("target",type=Path,help="target disk, for example /dev/vda")
    p.add_argument("--repository",type=Path,default=DEFAULT_REPOSITORY,help=argparse.SUPPRESS)
    p.add_argument("--manager",type=Path,default=DEFAULT_MANAGER,help=argparse.SUPPRESS)
    a=p.parse_args()
    print(json.dumps(install(a.repository,a.manager,a.target),indent=2,sort_keys=True))

if __name__=="__main__":
    main()
