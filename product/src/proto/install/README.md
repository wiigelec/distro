# Install prototype

The primary Install prototype now has a package-closed ISO path. See
`../bootstrap/README.md` for the Stage-0 trust boundary and closed pipeline.

```text
Build package repository
        |
        v
build_iso.py
        |
        v
bootable Archiso installer
        |
        v
install-distro TARGET
        |
        +-> partition target
        +-> create ext4 root
        +-> invoke Manage install system
        +-> install EXTLINUX
        `-> write boot configuration
```

The live ISO is only the installation environment. Target package payloads are
still installed exclusively through Manage.

## Arch host prerequisites

```sh
sudo pacman -S archiso syslinux qemu-system-x86
```

## Build the package repository

```sh
python3 product/src/proto/builder/system_fixture.py \
  --output /tmp/distro-system-repo
```

## Build the installer ISO

```sh
python3 product/src/proto/install/build_iso.py \
  --repository /tmp/distro-system-repo \
  --output /tmp/distro-installer.iso
```

The ISO bundles the prototype repository, `manage.py`, and the command
`/usr/local/bin/install-distro`.

## Boot the installer in QEMU

```sh
truncate -s 1G /tmp/distro-target.img

qemu-system-x86_64 \
  -m 1G \
  -cdrom /tmp/distro-installer.iso \
  -drive file=/tmp/distro-target.img,format=raw,if=virtio \
  -boot d
```

At the live root shell:

```sh
install-distro /dev/vda
```

The command is destructive to the selected target. It refuses non-block-device
targets and targets that already contain mounted filesystems.

For this prototype it creates a DOS/MBR partition table, one active Linux
partition, an ext4 filesystem labeled `distro-root`, invokes Manage to install
the `system` profile, and installs EXTLINUX. The installed boot configuration
uses `root=LABEL=distro-root`.

After installation reports `"status": "success"`, shut down the VM and boot the
target disk without the ISO:

```sh
qemu-system-x86_64 \
  -m 256 \
  -drive file=/tmp/distro-target.img,format=raw,if=virtio \
  -serial mon:stdio
```

The installed system should enter the BusyBox login shell and support:

```sh
ls -al /
```

## Earlier host-side install path

`install.py` and `vm_acceptance.py` remain as the previous milestone's direct
host-side install path for regression testing.

## Prototype limits

This milestone remains x86_64 with a BIOS-installed target, DOS/MBR, one ext4
root filesystem, and EXTLINUX. The historical `build_iso.py` path still uses Archiso, but the accepted
closure path builds the installer initramfs and ISO inside a Manage-created
Distro build root using packaged cpio/gzip/Syslinux/xorriso. GPT/UEFI target installation, encryption, swap, LVM/RAID, separate
`/boot`, networking configuration, users, locale, timezone, hostname,
recovery, and install resume remain outside this slice.
