# G2 installer prototype

This prototype extends `proto/g1-bootable` far enough to prove the
**Install -> Manage -> independently bootable target** path.

It is intentionally not a production installer. The first target is a BIOS/QEMU
machine with one disposable disk and one ext4 root partition.

## Prototype boundary

G2 reuses the G1 package/build/manage implementation.

The installer owns only installation orchestration:

1. select and destructively prepare the target disk;
2. create the target filesystem;
3. call the existing Manage prototype to install the package closure;
4. write target-specific filesystem configuration;
5. install the already-built BIOS GRUB implementation;
6. write a direct-kernel GRUB entry.

The installer does **not** unpack distro package artifacts itself.

## Additional package

`g2-installer.json` is generated from `g1-bootable.json` and adds `e2fsprogs`.
That gives the live installer environment `mkfs.ext4` while preserving the G1
bootable closure.

## Build the package repository

```sh
./product/scripts/build g2-installer
```

The repository must be complete before media construction.

## Build installer ISO

The initial media builder uses the installed G2 closure as an initramfs live
environment and uses the host's `grub-mkrescue`, `xorriso`, `cpio`, and `gzip`
tools to create BIOS-bootable media.

```sh
sudo python3 product/src/proto/g2_installer/build_iso.py   --output /tmp/distro-g2-installer.iso
```

The live environment contains the complete `g2-installer` closure, the generated
package repository, the current prototype `manage.py`, `/usr/bin/distro-install`,
and a minimal `/init` that boots directly to a root shell.

## First install proof

Boot the ISO with an empty VM disk. In the installer shell:

```sh
distro-install /dev/vda   --confirm-device /dev/vda   --yes-really-destroy
```

The redundant confirmation is deliberate. This command destroys the selected
device.

The script creates an MBR partition table with one bootable Linux partition,
formats it ext4, installs the `g2-installer` closure through Manage, writes
`/etc/fstab`, installs BIOS GRUB, and writes a GRUB configuration that boots the
installed kernel directly from the root filesystem.

After installation, shut down the VM, remove the ISO, boot from the virtual
disk, and verify the resulting distro system reaches the same G1 bootable-system
proof.

## Deliberately deferred

This prototype does not attempt to establish UEFI installation, GPT policy,
multiple filesystem or partition layouts, swap, encryption, networking, package
selection, user creation, installer UI, rescue mode, rollback, generalized
hardware discovery, or production-grade failure recovery.
