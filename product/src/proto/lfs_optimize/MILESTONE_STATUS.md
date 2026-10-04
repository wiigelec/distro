# LFS optimize prototype — milestone status

Last updated: 2026-10-03

Authoritative branch: `proto/lfs-optimize`

Recorded from HEAD: `b6d522100692e945fdec4869575c441e0e2b172f`

Roadmap:
`product/src/proto/docs/lfs-blfs-modernization-implementation-roadmap.md`

## Current milestone state

| Milestone | Status | Proof |
| --- | --- | --- |
| M1 — Model proof | COMPLETE | Version-independent normal-LFS package definitions plus development version manifest resolve successfully. |
| M2 — Execution proof | COMPLETE | Normal package executor builds, captures filesystem deltas, creates artifacts, realizes them, and verifies equivalence. |
| M3 — Normal-LFS proof | COMPLETE | All 80 final-system LFS packages execute through the same normal executor and can reconstruct a successful final filesystem. |
| M4 — Bootstrap proof | COMPLETE | Fresh Chapter 5–7 bootstrap hands directly to the normal executor; all 80 final-system packages build successfully without publication XML/book parsing. |
| M5 — Development proof | NEXT | Implement discovery → candidate → validation → promote/fail while leaving development unchanged on failure. |
| M6 — Release proof | NOT STARTED | Freeze validated development manifest and perform a clean full release build. |
| M7+ | NOT STARTED | Presentation, BLFS, hard-BLFS, and user-system proofs remain later roadmap milestones. |

## M4 proof evidence

M4 is orchestrated by:

`product/src/proto/lfs_optimize/lfs.py`

The successful proof was run with:

```sh
sudo python3 product/src/proto/lfs_optimize/lfs.py \
  --work /home/wiigelec/lfs-optimize/work-m4 \
  --cache /home/wiigelec/lfs-optimize/cache \
  --skip-tests \
  --fresh-artifacts
```

Observed proof properties:

- bootstrap completed from the normalized LFS 13.1-systemd bootstrap plan;
- bootstrap output was handed directly to `system.py`;
- the normal executor completed through `e2fsprogs`;
- top-level M4 status was `success`;
- final normal-system status was `success`;
- the run used `--fresh-artifacts`;
- `lfs.py` rejects a successful fresh-artifact proof if any normal package is a cache hit, so successful completion proves the normal package set was rebuilt rather than replayed from M3;
- normal package artifacts were created under `cache/m4-proof/artifacts`;
- successful package work directories were cleaned as packages completed.

Tests were intentionally skipped for this prototype proof with `--skip-tests`.

## Current architecture

Bootstrap path:

```text
bootstrap.py / bootstrap-13.1.json
        ↓
fresh Chapter 5–7 handoff root
        ↓
lfs.py
        ↓
system.py
        ↓
execute.py
        ↓
80 normal final-system packages
```

No publication XML is an execution input.

The normal package executor remains the shared Chapter 8+ executor. Bootstrap logic is kept separate rather than folded into `system.py`.

## Artifact/cache state

`execute.py` currently:

- snapshots filesystem state including file type, content, mode, numeric uid/gid, symlinks, and hardlink topology;
- represents changed/added paths plus explicit baseline deletions;
- preserves privileged mode bits;
- handles hardlink topology and stale-baseline hardlink splitting;
- allows legitimate absolute filesystem symlinks while rejecting relative symlink escapes;
- writes new artifacts to a temporary cache file;
- verifies realization equivalence before atomic cache promotion with `os.replace()`;
- reports cache hits as reused artifacts rather than falsely claiming a fresh equivalence comparison;
- cleans successful `root-after`, `root-test`, `root-realized`, and `stage` package work directories;
- preserves failed package work directories for diagnosis.

Cache schema version remains 4 so verified M3 artifacts were not invalidated unnecessarily.

## Source acquisition

Stable LFS 13.1 source acquisition uses the OSUOSL LFS package mirror MD5 index.

Policy:

- package source archives must resolve by MD5 in the stable LFS 13.1 mirror;
- auxiliary resources use the mirror when their MD5 is indexed there;
- otherwise auxiliary resources fall back to their canonical URL;
- downloaded resources are MD5 verified.

## Current authoritative development state

Version manifest:

`product/src/proto/lfs_optimize/versions/development.json`

Package set:

`product/src/proto/lfs_optimize/package-set.json`

The package set contains all 80 normal final-system packages in execution order.

Current development basis:

- Linux From Scratch
- `13.1-systemd`
- published `2026-09-01`

At this point there is only the authoritative development manifest. There is no candidate/discovery/promotion state yet.

## M5 starting point

Implement the first development-state vertical slice without changing the build engine:

```text
development manifest
        ↓
discovery
        ↓
candidate record/manifest
        ↓
candidate validation
       / \
 success  failure
   ↓        ↓
promote   development unchanged
```

Recommended first implementation:

1. Add a deterministic/manual discovery provider first.
2. Produce explicit candidate state rather than mutating `development.json`.
3. Validate a candidate using the existing resolver/executor path.
4. On success, promote candidate state into development explicitly.
5. On failure, persist useful failure evidence and leave development unchanged.
6. Prove both a successful promotion and a deliberate failure before adding scheduled or upstream-specific discovery providers.

Do not begin with GitHub/PyPI/FTP scraping. First prove the state machine and authority boundaries; external discovery providers should plug into that interface afterward.

## Important recent commits

- `b6d522100692e945fdec4869575c441e0e2b172f` — Add bootstrap-to-normal LFS proof driver.
- `93f9c1d438b6436897d96fb996593c72d35ace3b` — Harden artifact cache publication and cleanup.
- `5b59569688b4409639c65c28aee2844579c02aa5` — Allow root-relative absolute symlinks in artifacts.
- `de461f3a428bafac09fe6ee60dd575359ed3b2e6` — Normalize Groff paper size.
- `9b57a1ecf5187e73ed65e6917f154978b2431318` — Preserve privileged mode bits.
- `489144e11ccee5afbc4cd9bb5832bbed00bf059b` — Break stale baseline hardlinks before extraction.
- `61f151881238ff4ad26f82380467791ebbf613b5` — Preserve snapshot hardlink topology.

## Resume instruction

A fresh chat should begin by reading this file and the roadmap, verify the current `proto/lfs-optimize` HEAD, then proceed directly with M5 development-proof implementation using GVE for repository mutations.
