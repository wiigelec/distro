# G1 chroot prototype

This prototype explores the first Generation-1 package set from a clean branch
based on `main`.

Public prototype interface:

```sh
./product/scripts/build g1-chroot
./product/scripts/manage install g1-chroot
```

`g1-chroot` is a desired-state manifest. Each package entry contains exactly:

- package name;
- upstream discovery URL;
- management policy: `stable`, `lts`, or `bleeding-edge`.

The manifest does not pin concrete versions, checksums, build commands, or
recipes. Build owns those decisions and generated state.

Build currently performs two discovery stages for `stable` packages:

1. inspect the upstream release index and select the newest stable release
   archive;
2. download and hash that source, safely extract it, inspect the source tree for
   supported build-system markers and documentation, and emit a candidate recipe.

`lts` and `bleeding-edge` are recognized manifest values but intentionally fail
until their selection semantics are prototyped.

Run:

```sh
./product/scripts/build g1-chroot
```

By default generated source archives, extracted work trees, candidate recipes,
and the result record are written below `/tmp/distro-g1-chroot`.

Candidate recipes are evidence from source inspection, not yet accepted package
recipes. The next slice executes them in the Generation-0 Arch build environment
and uses real build failures or package-specific requirements to refine recipe
derivation.

The first functional target remains a chroot containing GNU Bash and GNU
Coreutils (`ls`) without BusyBox.
