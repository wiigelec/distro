# Bootstrap staging prototype

This branch carries prototype work for the compiler/bootstrap staging chain.
It is proof work, not an accepted product interface or normative bootstrap
specification.

## Stage model

The former **Stage 1a** is now **Stage 0**.

```text
Stage 0  foreign host -> runnable Distro chroot
         bash + coreutils + mandatory runtime closure

Stage 1  foreign host -> compiling Distro chroot
         Stage 0 + GCC/native toolchain closure

Stage 2  Stage 1 chroot -> bootable Distro host
Stage 3  Stage 2 host   -> native rebuild of the bootstrap chroot closure
Stage 4  Stage 3 chroot -> final Distro package set
```

Stage 0 is intentionally foreign-built. Its purpose is to establish the
smallest runnable Distro userspace boundary. Stage 1 grows that boundary into
a self-hosting build environment.

## Current Stage 0 prototype

`build-stage0.sh` uses a temporary cross-toolchain inside Bubblewrap to build:

- temporary Binutils and GCC under `~/distro-proto/tools`;
- Linux API headers and glibc into `~/distro-proto/chroot`;
- Bash and Coreutils for the target root.

The builder preserves completed-step stamps and package logs under
`~/distro-proto`.

Before each source fetch it prints a source header containing the source name,
URL, destination file, and whether the file is cached or being downloaded.
This keeps long source-preparation runs attributable in terminal logs.

Run:

```sh
product/src/proto/bootstrap/build-stage0.sh
```

Acceptance check:

```sh
sudo chroot ~/distro-proto/chroot
ls
```

Useful controls:

```sh
product/src/proto/bootstrap/build-stage0.sh --status
product/src/proto/bootstrap/build-stage0.sh --clean-from glibc
product/src/proto/bootstrap/build-stage0.sh --clean-all
```
