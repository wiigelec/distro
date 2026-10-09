# Distro bootstrap → Build chroot exploration

Status: **prototype hypothesis; not Product Design, Planning, or an accepted Functional Set**.
Proposed branch: `proto/distro-bootstrap-chroot` (branched from `main`).

## Directory layout

The three working phases follow the conceptual progression of LFS Chapters 5–7 without importing its package lists, recipes, or version pins:

- `cross-toolchain/`: active host-following manifest, runner and JSON recipes.
  - `cross-toolchain/host/`: B0 host qualification and isolation probes.
  - `cross-toolchain/experiments/`: retained historical B1 experiments (not the active version policy).
- `temporary-tools/`: reserved for target-executable temporary userspace.
- `extra-tools/`: reserved for native build tools and exploratory Build-chroot hypotheses.

From the repository root, run the active Binutils experiment with a fresh workspace:

```sh
python3 product/src/proto/distro_bootstrap_chroot/cross-toolchain/cross_runner.py \
  --package binutils --workspace /var/tmp/distro-cross-new \
  --out /tmp/distro-cross-result.json
```

Host versions are discovered on every run; there are no persistent version locks. Earlier B1 experimental scripts are preserved as historical evidence only.

## Question

What minimum independent bootstrap stages, tools, and package closure are needed to produce a Distro-native Build chroot and rebuild a representative package without an undeclared foreign-host dependency?

The `proto/lfs-optimize` branch is evidence for staged toolchain construction and validation methodology **only**. Do not import its package set, recipes, versions, source manifests, executable procedures, or normative assumptions. Any common upstream software must be separately justified and selected.

## Two different deliverables

1. **Temporary bootstrap toolset:** a foreign-host-assisted, pinned chain of temporary compilers, linkers, runtime libraries, and utilities, culminating in a runnable native build environment.
2. **Definitive Build chroot candidate:** a fresh root assembled from Distro-produced package artifacts using Manage. The bootstrap root must not become the definitive managed root by copying it.

## Experimental stage hypotheses

- B0 host qualification: supported host kernel/architecture and all required host capabilities explicitly measured.
- B1 cross foundation: produce a target linker/compiler and runtime interface without host-library leakage.
- B2 temporary userspace: compile sufficient target shell, filesystem, archive, and build capabilities to enter the target root.
- B3 native handoff: execute a target-native compiler and builder inside the isolated root; enumerate runtime linker closure.
- B4 managed package production: build an initial independently selected package set into verifiable immutable artifacts.
- B5 managed chroot realization: ask Manage to install the published closure into a fresh, empty root.
- B6 self-hosting probe: build and execute C and C++ probes inside that root; rebuild a selected representative source package and verify no unexpected host dependency.

These are *transitions and acceptance gates*, not a frozen stage ordering or recipe format. The number of compiler passes is a result of experimentation, not an inherited LFS requirement.

## Candidate capability assessment

`capabilities.json` enumerates needs without automatically selecting package names. `build-chroot-candidate.json` proposes a deliberately small, **unverified** package set for a GNU toolchain approach. It is not a dependency-complete package manifest, and it must not be represented as one.

Separate baseline tools from per-package build dependencies. Use package-runtime closure observations to promote items into the baseline only with justification. A chroot need not boot; it does not imply an init system, kernel package, or bootloader.

## Proof protocol

For each stage save: input digest, source provenance and checksum, command/env record, output file inventory, executable/runtime closure, result JSON, and failure diagnostics. Check isolation boundaries at stage handoff. Execute an independent cold rebuild before calling a phase proven. Verify that the managed root contains no inherited bootstrap files except those explicitly supplied by Distro packages. Build the same representative test workload in the managed root.

## Open design experiments

- Toolchain strategy: GNU/glibc versus alternatives, target triple, multi-pass needs, sysroot layout.
- Host bootstrap assumptions: trusted host compiler, static or dynamic bootstrap executables, kernel and minimum host tool versions.
- Build executor implementation and its interpreter/dependency closure.
- Initial package selection, source and version policy, package build order, runtime dependencies, and cross/native phases.
- How Build and Manage prototype interfaces pass immutable artifacts and installed metadata.
- Isolation method, pseudo-filesystem mounts, user IDs, root privileges, networking, cache trust, and contaminated-environment detection.
- Handling circular dependencies and ensuring a reproducible closure.

## Graduation criteria

A prototype result is ready for Product Design consideration only after explicit evidence for B0–B6, an independently derived package manifest with resolved closure, and a written account of unresolved assumptions. Acceptance to `main` requires the normal repository lifecycle; prototype success is not acceptance.
