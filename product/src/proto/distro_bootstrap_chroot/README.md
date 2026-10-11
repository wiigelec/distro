# Distro bootstrap → Build chroot exploration

Status: **prototype hypothesis; not Product Design, Planning, or an accepted Functional Set**.
Working branch: `proto/distro-bootstrap-chroot`.

## Three stages

The bootstrap has exactly three working stages, inspired only by the broad progression of LFS Chapters 5–7. Distro selects its own packages, versions, recipes and acceptance evidence.

1. **Cross-toolchain** (`cross-toolchain/`): qualify the foreign host; construct and validate the target assembler/linker, initial compiler, Linux API headers and libc interface. `host/` contains host qualification and isolation probes. `experiments/` retains historical observations; those records are not active build instructions.
2. **Temporary-tools** (`temporary-tools/`): construct a sufficient target-executable temporary userspace to support native work within an isolated target root. No runnable temporary-tools recipes have yet been accepted.
3. **Extra-tools** (`extra-tools/`): construct and validate native build capabilities, produce independently selected Distro package artifacts, and investigate realization of a distinct managed Build chroot. Package inventory and dependency closure remain hypotheses.

Validation is attached to each stage and its handoffs; the former numbered-state scheme is retired. Historical documents may retain legacy labels as archival evidence only.

## Current cross-toolchain execution

From the repository root, as a non-root user:

```sh
./product/scripts/build cross-toolchain --root ~/distro-bootstrap-chroot
```

`--root` is the bootstrap **project directory**, containing `root/` (installed filesystem) and `.distro-bootstrap/` (source workspaces, logs, results and stamps). The root is not yet the definitive managed Build chroot. The active manifest discovers host versions on each execution; it has no persistent version lock. Each completed package must carry its resolved source identity and digest as evidence, not as a future version-selection policy.

GCC and glibc use a canonical installed-root view at `/toolchain` inside build sandboxes. Linux API headers live at `/toolchain/usr/include`. Cross-toolchain acceptance requires a clean build, isolated compile/link/execute probes, target ELF and runtime inspection, a source provenance record, and an independent cold rebuild. A passing repository validation script alone does **not** prove those runtime requirements.

## Research question

What minimal independent toolchain, userspace, native tools and package closure can produce a Distro-native Build chroot that rebuilds a representative source package without undeclared foreign-host dependencies?

The `proto/lfs-optimize` branch informs validation methodology only. Do not import its package sets, recipes, version pins, source manifests, executable procedures, or normative assumptions.

## Two different deliverables

- **Temporary bootstrap toolset:** a foreign-host-assisted chain culminating in a runnable native build environment. It may have declared foreign-host dependencies during construction.
- **Definitive managed Build chroot:** a fresh root assembled by Manage from immutable Distro-produced package artifacts, never by copying the bootstrap root wholesale.

`extra-tools/capabilities.json` describes candidate capabilities without choosing packages automatically. `extra-tools/build-chroot-candidate.json` is a deliberately unverified package proposal, not a complete closure. Separate baseline capabilities from package-specific dependencies. A chroot need not boot and implies no kernel, init system or bootloader.

## Evidence and acceptance

For each stage retain input/source identities, authenticated or transport-only checksum provenance, build commands and environment, installed file inventory, executable dependency evidence, validation results and failure diagnostics. Test negative isolation cases and contamination paths; execute a cold rebuild before declaring the stage proven. For the definitive Build chroot, verify that no bootstrap-only files were inherited and rebuild a representative package using the managed installed closure.

Remaining research includes source-authentication trust, minimum supported host versions and kernels, cross/native dependency cycles, runtime linker closure, sandbox mounts and user IDs, executor requirements, and Manage/Build artifact interfaces. Prototype success is not acceptance to `main`; follow the repository lifecycle.
