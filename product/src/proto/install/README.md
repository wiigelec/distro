# Install v0 virtual-machine prototype

This prototype exercises the Install -> Manage boundary with a complete virtual
disk image.

Install v0 owns machine-level preparation:

- create a raw disk image;
- create a DOS/MBR partition table;
- create one bootable Linux partition;
- format the root partition as ext4;
- mount the target root;
- invoke Manage to install the `system` profile;
- install EXTLINUX and MBR boot code;
- write kernel boot configuration;
- cleanly unmount and detach the image.

Install does not unpack package artifacts itself. The `system` profile is a
prototype meta-package resolved by Manage:

```text
system
|- kernel
`- busybox
   |- musl
   `- base-files
```

The kernel package is produced by the fixture from Debian bookworm's cloud
kernel plus its generated initramfs. `base-files` supplies `/sbin/init`, which
starts a BusyBox login shell and reads `/etc/profile`.

## Host prerequisites

The prototype requires these host commands:

```text
sfdisk
losetup
mkfs.ext4
mount
umount
extlinux
qemu-system-x86_64
```

On Debian-family hosts these are provided by packages such as `util-linux`,
`e2fsprogs`, `extlinux`, `syslinux-common`, and `qemu-system-x86`.

## Build the repository

```sh
python3 product/src/proto/builder/system_fixture.py \
  --output /tmp/distro-system-repo
```

## Install a bootable raw disk image

The image path is replaced if it already exists.

```sh
sudo python3 product/src/proto/install/install.py \
  --repository /tmp/distro-system-repo \
  --image /tmp/distro.img \
  --size-mib 1024
```

## Boot and verify BusyBox `ls`

```sh
python3 product/src/proto/install/vm_acceptance.py \
  --image /tmp/distro.img
```

The acceptance runner boots QEMU with the image as a virtio disk, waits for the
BusyBox shell, sends `ls -al /` over the serial console, and succeeds only when
the expected root directories appear.

## Prototype limits

This slice is x86_64, BIOS, DOS/MBR, one ext4 root filesystem, raw images, and
EXTLINUX only. It deliberately does not yet cover GPT/UEFI, encryption, swap,
LVM/RAID, separate `/boot`, networking, users, locale, timezone, hostname,
recovery, or install resume.
