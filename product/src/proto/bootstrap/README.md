# Closed bootstrap prototype

This directory is the prototype's explicit bootstrap trust boundary.

The goal is not to pretend that a new distribution appears without a seed. The
goal is to make the seed finite, visible, and auditable, then require the
accepted build and installer-media paths below it to consume only Distro
packages.

```text
Arch host packages
      |
      | Stage-0 only
      v
bootstrap-tools.distro
============================= trust boundary
      |
      +-> Manage install build-system
      |       |
      |       v
      |   closed build root
      |       |
      |       +-> build musl + BusyBox packages
      |       +-> package bootstrap kernel
      |       `-> emit target Package DB
      |
      +-> generated installer repository
              |
              v
          Manage install installer-runtime
              |
              v
          installer root
              |
              | package-owned cpio/gzip/xorriso/syslinux
              v
          bootable installer ISO
```

## Stage-0

On the Arch development host, install only the bootstrap creator dependency:

```sh
sudo pacman -S arch-install-scripts
```

Create the seed repository:

```sh
sudo python3 product/src/proto/bootstrap/seed.py \
  --output /tmp/distro-seed-repo
```

`seed.py` uses `pacstrap` exactly once to create `bootstrap-tools`. The artifact
records `stage0=true`, `stage0_origin=arch-pacstrap`, and the explicit seed
package list. It also packages the prototype implementation under
`/opt/distro/proto`.

This is the only path in this milestone where Arch package payloads may enter
the trust chain.

## Closed pipeline

After the seed exists:

```sh
sudo python3 product/src/proto/bootstrap/closed_pipeline.py \
  --seed-repository /tmp/distro-seed-repo \
  --output /tmp/distro-closed \
  --iso /tmp/distro-closed-installer.iso
```

The host is now orchestration/substrate only. It supplies `chroot`, bind mounts,
network access, and storage. Build tools visible inside the build environment
come from `bootstrap-tools.distro`.

The pipeline:

1. uses Manage to install `build-system`;
2. audits every regular file and symlink in the build root;
3. enters that root and builds the target package repository;
4. creates an installer repository containing only Distro artifacts;
5. uses Manage to install `installer-runtime`;
6. audits the installer root;
7. enters the package-owned build root again;
8. creates the installer initramfs with packaged `cpio` and `gzip`;
9. creates the ISO with packaged Syslinux files and packaged `xorriso`.

Manage's generated `var/lib/distro/manage/installed.json` is the only
non-package regular file allowed by the root ownership audit.

Runtime pseudo-filesystems (`/dev`, `/proc`, `/sys`) and explicit input/output
bind mounts are treated as execution substrate, not root content.

## Boot the closed installer ISO

```sh
truncate -s 1G /tmp/distro-target.img

qemu-system-x86_64 \
  -m 2G \
  -cdrom /tmp/distro-closed-installer.iso \
  -drive file=/tmp/distro-target.img,format=raw,if=virtio \
  -boot d \
  -display gtk
```

At the installer shell:

```sh
install-distro /dev/vda
```

After success, boot the target disk without the ISO:

```sh
qemu-system-x86_64 \
  -m 256 \
  -drive file=/tmp/distro-target.img,format=raw,if=virtio \
  -serial mon:stdio
```

Then:

```sh
ls -al /
```

## Closure claim for this milestone

Below the Stage-0 line:

- the build root is assembled by Manage from Distro artifacts;
- musl and BusyBox are compiled inside that root;
- the target repository is generated inside that root;
- the installer root is assembled by Manage from Distro artifacts;
- ISO assembly programs and Syslinux boot files come from a Distro package;
- the installer ISO is generated inside the package-owned build root.

The kernel is still bootstrap-derived in this slice: it is copied from the
package-owned Stage-0 root into a normal Distro `kernel` artifact. Rebuilding
the kernel from source inside Distro is the next reduction of the bootstrap
trust set, not a hidden host dependency.
