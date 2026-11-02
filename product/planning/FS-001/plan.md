# FS-001 — Technical Plan: Cross-Toolchain Construction

## Goal and Shape

Implement Stage 1A via `product/scripts/build cross-toolchain --root <rootdir>` through the shared Build engine and sandboxed host execution. No independent Bootstrap engine or package-specific commands in Build application source. The initial reference is the **released LFS 13.1-systemd Chapter 5** (`https://www.linuxfromscratch.org/lfs/view/13.1-systemd/chapter05/chapter05.html`), used as a technical recipe reference rather than a second Design authority.

## Target and Host Baseline

FS-001 initially supports an **x86_64 Linux host producing an x86_64 GNU/Linux toolchain**. Determine the host machine triplet via the host GCC (`gcc -dumpmachine`); normalize its CPU portion to `x86_64` and use the **cross target triplet `x86_64-distro-linux-gnu`**, passing it consistently to Binutils, GCC, and glibc configure steps. Distinct host and target triplets provide the cross-compiler namespace even on matching architectures. The target triplet's vendor token is a Planning convention, not a claim of existing toolchain compatibility; recipes must confirm that the selected upstream releases accept it. Any necessary canonicalization adjustment returns to Planning rather than silently replacing the target identity.

Require the essential host capabilities from LFS 13.1 Chapter 2 host requirements (compiler, C++ compiler, binutils, make, shell, tar, decompression, patch, bison, gawk, etc.) and Bubblewrap (`bwrap`) with working unprivileged user and mount namespaces, plus an accessible writable workspace with enough free space. Build performs preflight checks before modifying `root/` or publishing artifacts. Host packages remain host-provided capabilities, not Distro manifest dependencies. Use the published LFS 13.1 Chapter 2 minimum host-tool versions as mandatory initial qualification floors, not optional recommendations. Preflight must check the required tool versions and that the host C and C++ compilers can actually compile and run minimal native tests; it must also execute a Bubblewrap unprivileged user/mount namespace and filesystem-mount probe. Reject missing, underspecified, incompatible or nonfunctional capabilities with a diagnostic before constructing or installing the toolchain. Build does not implement a host package manager.

## Workspace and Stage Data Flow

`--root` is the workspace, not an installation prefix. The workspace contains `build/` for downloaded/extracted sources and compilation, `root/` for the installed target `/` hierarchy, and `artifacts/` for archives of `root/`. Resolve the complete selected package sequence and prerequisites before construction. For each step, acquire and verify its selected sources before extracting them into its isolated source directory, prepare its build directory, and only then execute its recipe. A source verification failure aborts the stage without publishing an artifact. After all steps, verify the toolchain and archive `root/` only. Build workspace paths are never included in the handoff archive.

## Initial Package Versions and Construction Sequence

Pin the initial package selection to the released LFS 13.1-systemd Chapter 5 reference set and commit these literal versions to `product/src/build/bootstrap/cross-toolchain/lists/cross-toolchain.yaml`:

| Ordered recipe selection | Manifest identity | Version |
| --- | --- | --- |
| Binutils pass 1 | `binutils` | `2.47` |
| GCC pass 1 | `gcc` | `16.2.0` |
| Linux API headers | `linux` | `7.1.8` |
| glibc | `glibc` | `2.44` |
| libstdc++ from GCC sources | `gcc` | `16.2.0` |

The two GCC selections reference the **same authoritative GCC manifest and exact source version** but select distinct Bash recipes. An ordered list may therefore contain repeated package identity for separate construction steps; treat each selected step as a distinct execution node while retaining a single source and dependency authority. GCC supporting source components (such as GMP, MPFR, and MPC if used by the pinned GCC recipe) must have verified upstream source identities; any in-tree prerequisites downloaded by the recipe require a documented verified-source handoff from Build, not unverified recipe downloads. The initial GCC pass uses pinned, verified in-tree GMP `6.3.0`, MPFR `4.2.2`, and MPC `1.4.1` sources, extracted by Build beneath the GCC source tree as `gmp/`, `mpfr/`, and `mpc/`. These are supplementary verified inputs, not independently executed Stage 1A list steps; host-development-library substitution is not permitted for this baseline. GCC pass 1 receives its own fresh GCC 16.2.0 extraction and a separate out-of-tree build directory, with verified GMP/MPFR/MPC prepared inside that source tree. The later libstdc++ step receives a **different, freshly extracted, clean GCC 16.2.0 source tree** and its own independent build directory. It may use the installed pass-1 cross-compiler and other declared outputs, but shall not reuse or depend upon the pass-1 extracted source directory, modified source files, generated files, or build directory. It receives only verified supplemental inputs its own recipe actually requires. The verified original GCC archive may be reused as input for both independent extractions.

This sequence is a *planning baseline*, not a claim that these versions have been experimentally built in Distro yet. The precise LFS configure flags and compatibility patches reside in the corresponding Bash recipes; no instruction text is embedded in lists or manifests. The Stage 1A package set stops after libstdc++ construction; Stage 1B begins the temporary-tools sequence.

## Manifest, List, and Ordering Contract

Each YAML manifest under `product/src/build/packages/` is uniquely identified by package name and owns upstream source locations/name templates, verification schemes (initially `sha256`), and all dependency declarations. The YAML package list owns each selected version and its literal SHA-256 digest. Manifest source templates may substitute only the selected `{version}`. Supplementary GCC source identities, URL templates, and verification schemes are declared in the GCC manifest; their selected versions and literal SHA-256 digests are declared in the list under the GCC pass-1 step; Build verifies the supplementary archives and prepares all three for GCC pass 1 in that step's private source tree; the clean libstdc++ extraction is independent and receives only supplementary sources needed by its recipe. The `cross-toolchain` YAML list contains ordered entries with `name`, quoted `version`, literal `checksum`, and repository-relative `recipe`, plus an optional explicit step identifier for repeated GCC selection. The GCC pass-1 step also owns `supplements` entries mapping each manifest-declared supplementary identity to a quoted `version` and literal `checksum`; the later libstdc++ step uses the same GCC archive checksum but no supplemental inputs. No list entry may declare dependencies, redefine source URLs or verification algorithms, or embed build commands. Every manifest dependency needed to execute a selected step must be resolved to an explicitly selected list version or a preflight-checked host capability defined by the manifest's build-tool category. Manifest dependency relationships control prerequisite validity; the prescribed step ordering resolves sequence among same-package phases. Reject unresolved or cyclic prerequisites. Avoid a general conditional-expression system unless this selected sequence demonstrates its need.

## Host-Execution Sandbox and Portability

Use Bubblewrap (`bwrap`) as the initial shared host-execution sandbox backend. Preflight must confirm unprivileged user/mount namespace availability and enforce sandbox setup before any package recipe runs; missing or unusable isolation fails closed without an unrestricted fallback. Run as an unprivileged user. This sandbox is the execution boundary for host-based Stage 1A recipes, not `distro-buildroot` execution and not a second Build engine.

Each recipe subprocess is launched by Build directly as `bash` inside its own Bubblewrap sandbox. Clear the inherited environment, then explicitly set the documented `DISTRO_*` contract, a fixed `PATH` containing `/toolchain/tools/bin` and qualified host executable locations, `HOME=/work`, `TMPDIR=/tmp`, and `LC_ALL=C`. Deny implicit leakage of `CPATH`, `LIBRARY_PATH`, `LD_LIBRARY_PATH`, `PKG_CONFIG_PATH`, compiler overrides, and similar host variables unless deliberately qualified and provided in the explicit contract. The qualified host tools and their runtime libraries are mounted read-only; host `/usr`, `/bin`, `/lib*`, and necessary `/etc` entries may be exposed read-only as required, but do not expose host `/` as a writable or automatically inherited mount. Restrict host resource mounts to the qualified allowlist. Use private `/tmp` and `/run`, a private process mount, and separate namespaces as supported by the chosen backend. Network access is not required by recipes because Build acquires and verifies each step’s sources before executing that recipe; disable recipe network access.

The selected host workspace `rootdir` is exposed through controlled writable mounts: `build/` at `/work` and the installed filesystem `root/` at `/toolchain`. Build never grants write access to the actual host system directories. Installation destinations, configure `--prefix` paths, sysroot arguments, GCC search paths, and the executable PATH refer only to these sandbox-visible paths. Specifically the installed cross-tools live in `/toolchain/tools/`, and target headers and libraries in the corresponding `/toolchain/usr` and `/toolchain/lib*` hierarchy. The exported archive still contains only the contents of host `rootdir/root/`, not a `/toolchain` enclosing directory. Host absolute workspace paths may not be embedded in the artifact as a runtime requirement. Distinguish sandbox-visible **build-time sysroot and compiler lookup paths** (for example `/toolchain/usr/include`, `/toolchain/usr/lib*`) from **target-runtime ELF paths** (for example `/lib64/ld-linux-x86-64.so.2`, where appropriate). The ELF interpreter is interpreted relative to the eventual target system root, not prefixed with `/toolchain`; the cross-linker must nevertheless find the corresponding interpreter, crt objects and libraries beneath the sandbox-mounted target sysroot. Validate compiler search paths and final ELF interpreter/NEEDED entries independently, and reject host-library fallback without incorrectly rejecting valid target-runtime absolute paths.

The original `rootdir` is *not* a required extraction location. Before publishing, restore the **unpublished candidate archive** into a second workspace with a different absolute host path; make the original workspace unavailable to the functional test; bind the restored `root/` at the same `/toolchain` sandbox location, read-only for verification, and perform actual target C and C++ compilation/linking against the restored target interfaces. Inspect compiler sysroot/search paths and ELF properties to reject references that depend on the original host workspace or host `/usr` libraries. A successful file extraction or a compile run still accessing original workspace paths does not count as portability. Stage 1B itself need not be implemented.

The writable installation root is exposed only for construction, whereas verification can mount it read-only. Confirm isolation before construction with negative probes: designated system paths are not writable; deliberately injected host environment values are absent; absolute staging paths resolve inside sandbox; unavailable namespaces or mount setup cause a nonzero failure. The sandbox is intended to prevent accidental host modification and contamination, not to assert containment of malicious recipes.

## Bash Recipe Execution Interface

Inside Bubblewrap, execute each recipe with `bash <sandbox-absolute-recipe-path>` as a separate subprocess, no generated intermediary script and no command-language translation. Bind the repository recipes read-only into the sandbox and set working directory to the per-step build directory under `/work`. Supply the following exported environment contract:

| Variable | Meaning |
| --- | --- |
| `DISTRO_SOURCE_DIR` | Sandbox-visible verified/extracted source tree under `/work` |
| `DISTRO_BUILD_DIR` | Sandbox-visible writable construction directory under `/work` |
| `DISTRO_ROOT_DIR` | Sandbox-visible `/toolchain` installation filesystem root |
| `DISTRO_TARGET` | Exact `x86_64-distro-linux-gnu` toolchain target triplet |
| `DISTRO_PACKAGE_NAME` | Authoritative manifest identity |
| `DISTRO_PACKAGE_VERSION` | Exact list-selected version |
| `DISTRO_STEP_ID` | Unique step identity, including repeat GCC phases |
| `DISTRO_TOOLS_DIR` | Sandbox-visible `/toolchain/tools` cross-toolchain prefix |

Provide the controlled sandbox PATH beginning with `/toolchain/tools/bin` when available and followed by qualified read-only host tool paths. Recipes themselves specify install prefix, sysroot, configure flags, make arguments, patches and cleanup, and must confine their installed outputs to the sandbox-mounted `DISTRO_ROOT_DIR`. The ordinary `bash` script remains independently runnable if a caller supplies this contract and source/build trees. For multi-source GCC support, Build prepares declared verified supplementary sources before recipe execution and supplies their documented locations; no recipe performs implicit unverified downloads.

## Source Acquisition and Verification

Use release archives, not Git checkouts. Retrieve the manifest's expanded URL, verify its **required literal SHA-256 digest** against the fetched bytes before extraction, and reject absent, malformed, or mismatched digests. Selected versions never float or auto-update. Archive extraction must reject absolute paths and parent-directory traversal that could escape `build/`. Checksums are copied from independently verified upstream metadata before Build work starts; placeholder checksum values never count as verified configuration. If a selected archive needs an upstream patch, treat its source/digest as explicit verified input, with recipe-owned patch application.

## Artifact and Failure Contract

Produce a **POSIX pax-compatible tar archive compressed with xz**, named `cross-toolchain.tar.xz`, under `rootdir/artifacts/`. Archive paths are relative to the contents of `rootdir/root/` (not prefixed with `root/`), with symlinks and executable modes preserved. Stage 1B will extract into its installed filesystem root; it must not need `build/`. Archive publication is transactional: create a candidate tar.xz archive at a temporary path under `artifacts/`, verify its readability and safe relative entry names, restore this **candidate** into a differently located workspace and complete all restored-toolchain functional and isolation tests, then atomically replace the final `artifacts/cross-toolchain.tar.xz` only after every gate passes. The final named archive is not an input to its own pre-publication verification. A failed candidate remains unpublished. Never claim a stale, partial, or failed artifact as successful; a failed run exits nonzero, and an existing artifact is not confused with the failed run. An implementation can use a fresh staging root per run to prevent accidental mixing with earlier contents while preserving unrelated user files.


### Stage 1A Handoff Metadata (FS-001 amendment)

Alongside `artifacts/cross-toolchain.tar.xz`, Stage 1A shall emit
`artifacts/cross-toolchain.json` (UTF-8 JSON, `schema_version: 1`). The JSON
is the machine-readable completion marker for this handoff, not a package
manifest and not part of the installed filesystem archive. Required fields:

- `artifact`: type `cross-toolchain`, stage `1A`, basename, `tar.xz` format,
  archive SHA-256 and size in bytes.
- `toolchain`: selected target triplet, sandbox sysroot `/toolchain`, and tools
  prefix `/toolchain/tools`.
- `sources`: ordered list of selected step IDs, authoritative package identities,
  selected versions, source SHA-256 values, recipe basenames, and selected
  supplementary source identities, versions and SHA-256 values.
- `build`: UTC creation timestamp, duration, qualified host GCC triplet, Git
  revision if available, and three-state Git working-tree cleanliness (true,
  false, or null if it cannot be established). A commit SHA does not claim
  complete reproducibility when the working tree is dirty.
- `verification`: successful initial functional and restored-toolchain checks.

Build derives source metadata from the selected list, not a parallel definition.
It creates and verifies an unpublished archive candidate, generates metadata
from the verified candidate, checks their agreement, then publishes the archive
before publishing metadata **last** via a same-filesystem rename. Two renames
are not atomically paired; therefore the metadata file is the sole completion
marker and consumers must require both files and check the metadata SHA-256
and size against the archive. Build refuses an existing named archive or
metadata file, and failure before publication leaves no valid completed handoff.
A consumer must not treat an archive alone as a usable handoff. Actual Stage 1B
consumption remains out of FS-001 scope.

## Functional Evidence

Successful recipe exit status alone is insufficient. Before archive publication, check: (1) expected target-prefixed assembler, linker, and GCC executable exist and report the selected target; (2) GCC can compile a minimal C source into a relocatable object and `readelf` confirms the selected x86-64 ELF machine; (3) GCC's search/sysroot paths resolve intended target headers and libraries beneath the installed filesystem and not host `/usr/include` or host libraries; (4) the initial glibc headers, crt objects, dynamic linker and libc needed for Stage 1B are installed; (5) a minimal dynamically linked C program can be linked with those target interfaces, with ELF interpreter/library references pointing to target filesystem semantics. Validate C++ include/library availability from the libstdc++ step with a small C++ compile/link check. Do not execute target binaries or claim Stage 1B was run. Check extraction of the unpublished candidate archive into a second, differently located workspace preserves paths, symlinks, and key toolchain executables; the restored toolchain must pass compile/link checks inside a fresh sandbox with the original workspace inaccessible.

## Validation and Lifecycle

Build registers native validation tasks for active mechanically evaluated requirements and exact bindings in `product/validation/requirement-evaluation.json`. Run `./scripts/validate`, review functional evidence, and conduct semantic Build Review against accepted Design, scope, Plan and requirements. The active M/B requirements need not be falsely marked complete at the Planning-only commit; no PR acceptance or Build authorization follows from merely publishing this draft.

## Implementation Boundaries and Sequence

Implement only shared host execution exercised by Stage 1A, not chroot/buildroot execution, Manage package creation, Stage 1B, version discovery or host package installation. First establish source/list/manifest parsing, verified GCC support source handling, Bubblewrap preflight and sandbox isolation, then the recipe contract and actual selected tools, then artifact export and functional checks, then mechanical requirement bindings. Build retains ordinary implementation choices (retry policy, logging, internal modules) that preserve the specified contracts.
