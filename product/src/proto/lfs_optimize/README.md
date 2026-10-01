# LFS optimize prototype

This prototype implements the proof milestones in
`product/src/proto/docs/lfs-blfs-modernization-implementation-roadmap.md` from a clean
implementation line. Mechanics from earlier prototype branches may be reused
where they fit this architecture, but their package-management semantics are
not inherited.

## Milestone 1 — model proof

The first proof represents six normal Chapter 8 LFS packages:

- zlib
- bash
- coreutils
- grep
- gzip
- make

Package definitions are version-independent. They preserve build procedures,
structured execution context, dependency classes, package descriptions,
document identities, and installed-item descriptions. `versions/development.json`
selects the concrete versions, sources, checksums, source sizes,
version-specific resources, and reference build metrics for the current
development state.

`resolve.py` combines a package definition with the selected development
version and emits the resolved package description consumed by later
milestones.

Run:

```sh
python3 product/src/proto/lfs_optimize/validate.py
python3 product/src/proto/lfs_optimize/resolve.py
python3 product/src/proto/lfs_optimize/resolve.py --package bash
```

The source reference for this proof is Linux From Scratch
r13.1-18-systemd, using the final-system Chapter 8 package instructions.

## Build/install artifact contract

Normal LFS/BLFS installation semantics remain authoritative. Later execution
milestones insert a transparent artifact boundary between a package's install
step and the target filesystem:

```text
build/test
    |
install into staging tree
    |
tar.xz cache artifact
    |
extract into target filesystem
```

The default `tar.xz` is only the staged filesystem tree. It has no
distro-specific metadata, dependency records, file ownership database, or
package-manager state.

A valid cached artifact may replace repeating the corresponding package build
when resuming a system build. Future configurable package-management
implementations may replace the default archive/extract realization step
without changing the authoritative package build definition.

Milestone 1 does not execute package builds. Staging, artifact creation,
caching, extraction, and execution are Milestone 2 concerns.

Milestone 1 is complete when validation proves that all six representative
packages retain the modeled build and render semantics required by the
roadmap without moving concrete version/source selection into package
definitions.
