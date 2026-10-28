# FS-001 — Technical Plan: Cross-Toolchain Construction

## Goal and Shape

Implement Stage 1A via `product/scripts/build cross-toolchain --root <rootdir>` through the shared Build engine and host execution. No independent Bootstrap engine or package-specific commands in Build application source. The initial reference is the **released LFS 13.1-systemd Chapter 5** (`https://www.linuxfromscratch.org/lfs/view/13.1-systemd/chapter05/chapter05.html`), used as a technical recipe reference rather than a second Design authority.

## Target and Host Baseline

FS-001 initially supports an **x86_64 Linux host producing an x86_64 GNU/Linux toolchain**. Determine the host machine triplet via the host GCC (`gcc -dumpmachine`); normalize its CPU portion to `x86_64` and use the **cross target triplet `x86_64-distro-linux-gnu`**, passing it consistently to Binutils, GCC, and glibc configure steps. Distinct host and target triplets provide the cross-compiler namespace even on matching architectures. The target triplet's vendor token is a Planning convention, not a claim of existing toolchain compatibility; recipes must confirm that the selected upstream releases accept it. Any necessary canonicalization adjustment returns to Planning rather than silently replacing the target identity.

Require the essential host capabilities from LFS 13.1 Chapter 2 host requirements (compiler, C++ compiler, binutils, make, shell, tar, decompression, patch, bison, gawk, etc.) and an accessible writable workspace with enough free space. Build performs preflight checks before modifying `root/` or publishing artifacts. Host packages remain host-provided capabilities, not Distro manifest dependencies. Exact minimal host tool versions can follow the pinned LFS 13.1 host requirements, with a diagnostic on mismatch; Build does not implement a host package manager.

## Workspace and Stage Data Flow

`--root` is the workspace, not an installation prefix. The workspace contains `build/` for downloaded/extracted sources and compilation, `root/` for the installed target `/` hierarchy, and `artifacts/` for archives of `root/`. Resolve selected packages; fetch and verify all required sources; extract into isolated package source directories; prepare out-of-tree build directories when needed; run recipes on the host in prerequisite order; verify toolchain; then archive `root/` only. Build workspace paths are never included in the handoff archive.

## Initial Package Versions and Construction Sequence

Pin the initial package selection to the released LFS 13.1-systemd Chapter 5 reference set and commit these literal versions to `product/src/build/lists/cross-toolchain.yaml`:

| Ordered recipe selection | Manifest identity | Version |
| --- | --- | --- |
| Binutils pass 1 | `binutils` | `2.47` |
| GCC pass 1 | `gcc` | `16.2.0` |
| Linux API headers | `linux` | `7.1.8` |
| glibc | `glibc` | `2.44` |
| libstdc++ from GCC sources | `gcc` | `16.2.0` |

The two GCC selections reference the **same authoritative GCC manifest and exact source version** but select distinct Bash recipes. An ordered list may therefore contain repeated package identity for separate construction steps; treat each selected step as a distinct execution node while retaining a single source and dependency authority. GCC supporting source components (such as GMP, MPFR, and MPC if used by the pinned GCC recipe) must have verified upstream source identities; any in-tree prerequisites downloaded by the recipe require a documented verified-source handoff from Build, not unverified recipe downloads. Host-provided development libraries may instead be used where compatible with LFS 13.1 and documented by preflight.

This sequence is a *planning baseline*, not a claim that these versions have been experimentally built in Distro yet. The precise LFS configure flags and compatibility patches reside in the corresponding Bash recipes; no instruction text is embedded in lists or manifests. The Stage 1A package set stops after libstdc++ construction; Stage 1B begins the temporary-tools sequence.

## Manifest, List, and Ordering Contract

Each YAML manifest under `product/src/build/packages/` is uniquely identified by package name and owns upstream source locations/name templates, SHA-256 source digests, and all dependency declarations. Manifest source templates may substitute only the selected `{version}`. The `cross-toolchain` YAML list contains ordered entries with `name`, quoted `version`, and repository-relative `recipe`, plus an optional explicit step identifier for repeated GCC selection. No list entry may declare dependencies or embed build commands. Every manifest dependency needed to execute a selected step must be resolved to an explicitly selected list version or a preflight-checked host capability defined by the manifest's build-tool category. Manifest dependency relationships control prerequisite validity; the prescribed step ordering resolves sequence among same-package phases. Reject unresolved or cyclic prerequisites. Avoid a general conditional-expression system unless this selected sequence demonstrates its need.

## Bash Recipe Execution Interface

Execute each recipe with `bash <absolute-recipe-path>` as a separate subprocess, no generated intermediary script and no command-language translation. Set working directory to the per-step build directory. Supply the following exported environment contract:

| Variable | Meaning |
| --- | --- |
| `DISTRO_SOURCE_DIR` | Absolute verified/extracted source tree for this step |
| `DISTRO_BUILD_DIR` | Absolute writable construction directory for this step |
| `DISTRO_ROOT_DIR` | Absolute `rootdir/root` installation filesystem root |
| `DISTRO_TARGET` | Exact `x86_64-distro-linux-gnu` toolchain target triplet |
| `DISTRO_PACKAGE_NAME` | Authoritative manifest identity |
| `DISTRO_PACKAGE_VERSION` | Exact list-selected version |
| `DISTRO_STEP_ID` | Unique step identity, including repeat GCC phases |
| `DISTRO_TOOLS_DIR` | Absolute `rootdir/root/tools` cross-toolchain prefix |

Provide a deterministic PATH beginning with the constructed `root/tools/bin` when available and followed by the qualified host tools. Recipes themselves specify install prefix, sysroot, configure flags, make arguments, patches and cleanup, and must confine their installed outputs to `DISTRO_ROOT_DIR`. The ordinary `bash` script remains independently runnable if a caller supplies this contract and source/build trees. For multi-source GCC support, Build prepares declared verified supplementary sources before recipe execution and supplies their documented locations; no recipe performs implicit unverified downloads.

## Source Acquisition and Verification

Use release archives, not Git checkouts. Retrieve the manifest's expanded URL, verify its **required literal SHA-256 digest** against the fetched bytes before extraction, and reject absent, malformed, or mismatched digests. Selected versions never float or auto-update. Archive extraction must reject absolute paths and parent-directory traversal that could escape `build/`. Checksums are copied from independently verified upstream metadata before Build work starts; placeholder checksum values never count as verified configuration. If a selected archive needs an upstream patch, treat its source/digest as explicit verified input, with recipe-owned patch application.

## Artifact and Failure Contract

Produce a **POSIX pax-compatible tar archive compressed with xz**, named `cross-toolchain.tar.xz`, under `rootdir/artifacts/`. Archive paths are relative to the contents of `rootdir/root/` (not prefixed with `root/`), with symlinks and executable modes preserved. Stage 1B will extract into its installed filesystem root; it must not need `build/`. Archive publication is transactional: write to a temporary path, verify archive readability and safe relative entry names, and atomically replace the final artifact on success. Never claim a stale, partial, or failed artifact as successful; a failed run exits nonzero, and an existing artifact is not confused with the failed run. An implementation can use a fresh staging root per run to prevent accidental mixing with earlier contents while preserving unrelated user files.

## Functional Evidence

Successful recipe exit status alone is insufficient. Before archive publication, check: (1) expected target-prefixed assembler, linker, and GCC executable exist and report the selected target; (2) GCC can compile a minimal C source into a relocatable object and `readelf` confirms the selected x86-64 ELF machine; (3) GCC's search/sysroot paths resolve intended target headers and libraries beneath the installed filesystem and not host `/usr/include` or host libraries; (4) the initial glibc headers, crt objects, dynamic linker and libc needed for Stage 1B are installed; (5) a minimal dynamically linked C program can be linked with those target interfaces, with ELF interpreter/library references pointing to target filesystem semantics. Validate C++ include/library availability from the libstdc++ step with a small C++ compile/link check. Do not execute target binaries or claim Stage 1B was run. Check archive extraction in a separate temporary directory preserves paths, symlinks, and key toolchain executables.

## Validation and Lifecycle

Build registers native validation tasks for active mechanically evaluated requirements and exact bindings in `product/validation/requirement-evaluation.json`. Run `./scripts/validate`, review functional evidence, and conduct semantic Build Review against accepted Design, scope, Plan and requirements. The active M/B requirements need not be falsely marked complete at the Planning-only commit; no PR acceptance or Build authorization follows from merely publishing this draft.

## Implementation Boundaries and Sequence

Implement only shared host execution exercised by Stage 1A, not chroot/buildroot execution, Manage package creation, Stage 1B, version discovery or host package installation. First establish source/list/manifest parsing and preflight, then the recipe contract and actual selected tools, then artifact export and functional checks, then mechanical requirement bindings. Build retains ordinary implementation choices (retry policy, logging, internal modules) that preserve the specified contracts.
