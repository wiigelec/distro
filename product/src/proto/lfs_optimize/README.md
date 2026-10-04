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

## Milestone 2 — execution proof

`execute.py` consumes only the resolved normalized package model. It does not
parse LFS XML or synthesize an independent recipe.

The execution proof uses a complete LFS-compatible filesystem tree supplied
with `--root`. The tree is fingerprinted, cloned, and used as the chroot in
which the original LFS commands run. `/dev`, `/dev/pts`, `/proc`, `/sys`, and
`/run` are temporary execution mounts and are excluded from the captured
filesystem result.

After a successful build, the executor compares the cloned root with the
baseline and materializes only new or changed filesystem objects into a
staging tree:

```text
resolved package + baseline root
        |
fetch / checksum sources
        |
clone baseline root
        |
execute original commands in cloned chroot
        |
filesystem delta
        |
staging tree
        |
tar.xz cache artifact
        |
optional extraction into target root
```

Test steps execute in a disposable clone of the built root. Their success or
failure is recorded. Changes inside the package source/build tree are copied
back before later phases so test-generated build state remains available to
installation, while test-only mutations elsewhere in the system root are
discarded. This keeps artifacts such as temporary files or account/group
database backups out of the package payload without changing package build
semantics.

The archive contains only filesystem payload. The result JSON and build log
remain external evidence; they are not embedded package metadata.

Cache identity includes the resolved package definition, whether tests were
enabled, a content fingerprint of the baseline execution root, and an explicit
cache schema version. A cached artifact is therefore not reused across a
materially different baseline root or across an incompatible artifact contract.

Artifact snapshots and realization preserve file type, content, mode, numeric
UID/GID ownership, symlink targets, and hardlink topology. Generated artifacts
are path/link validated and then extracted with trusted metadata semantics so
numeric ownership is not sanitized away. After each cache miss, the executor
clones the original baseline again, realizes the new artifact into that clone,
and requires the resulting snapshot to equal the directly installed build
snapshot before reporting success.

Modification times are not part of the Milestone 2 equivalence contract.
Changed special filesystem objects remain unsupported and cause execution to
fail rather than being silently approximated.

A metadata-free tar archive cannot express deletion of a file that existed in
the baseline root. The proof executor rejects such a result rather than hiding
that semantic mismatch.

Inspect an execution plan without root access:

```sh
python3 product/src/proto/lfs_optimize/execute.py --package grep --plan
```

Execute against an LFS-compatible root:

```sh
sudo python3 product/src/proto/lfs_optimize/execute.py \
  --package grep \
  --root /path/to/lfs-root \
  --work /tmp/lfs-optimize-work \
  --cache /tmp/lfs-optimize-cache
```

Use `--realize-to` to extract the resulting cached filesystem artifact into a
target root after a successful build.


Milestone 2 is complete: the normalized package model has been proven through
execution, artifact capture, cache reuse, and realization equivalence.

## Milestone 3 — normal-LFS proof

Milestone 3 expands the proven package executor from isolated package builds to
the complete normal final-system LFS package set.

`system.py` is the first system-level slice. It resolves the package set in its
declared order, clones the supplied baseline once, and executes each package
against the progressively realized system root:

```text
baseline root
    |
package 1 -> artifact -> realize
    |
package 2 -> artifact -> realize
    |
...
    |
normal LFS system
```

The caller's baseline root is never modified. The progressive result is kept
under the system work directory, while each package continues to use the
Milestone 2 executor and artifact contract unchanged.

Inspect the ordered system plan without root access:

```sh
python3 product/src/proto/lfs_optimize/system.py --plan
```

Execute the currently modeled package set:

```sh
sudo python3 product/src/proto/lfs_optimize/system.py \
  --root /path/to/lfs-root \
  --work /tmp/lfs-optimize-work \
  --cache /tmp/lfs-optimize-cache
```

The next Milestone 3 work is package-model expansion until every normal LFS
final-system package participates in this same ordered execution path.

## Milestone 5 — development proof

`development.py` adds an explicit development-state workflow without changing
the normal build engine:

```text
accepted development -> discovery -> candidate -> validation -> promote/fail
```

The first proof uses LFS 13.0-systemd as historical accepted state and the
current LFS 13.1-systemd state as the candidate. The 13.0 fixture is state
input only; candidate validation uses the existing normalized resolver and
system executor.

Plan-only validation is intentionally non-promotable. Promotion requires a
successful full system build with tests enabled, and also requires the
development/package-set hashes observed during discovery to remain unchanged.

Test failures are review evidence, not automatic build termination. The
executor records the failed test command and exit status, marks the package,
system, and candidate validation `review_required`, and continues through
installation and subsequent packages. Prepare/configure/build/install/system
command failures remain fatal. Promotion may therefore carry unresolved test
review evidence for later maintainer review.
