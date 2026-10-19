# FS-001 — Bootstrap Plan

## Intent and governing boundaries

This Plan realizes `functional-set.md` at Design revision `12e71d53fde329b16b14ed8103136443696efa70`. Build, Manage, and Install remain distinct authorities. Bootstrap construction roots are temporary and must not become an alternative permanent package format or package-management authority. A definitive Build chroot is created by Manage from Distro-produced packages, not by copying the temporary chroot. M4 must supply the capability to create that Build chroot and produce native packages; M5 must demonstrate those capabilities *from the installed VM*.

## Technical realization by milestone

### M1 — Cross-toolchain

**Result and boundary.** M1 produces a validated Distro-targeting cross-toolchain, target headers and C runtime interface sufficient for M2. It is not the definitive Distro Build chroot or an installed system. Its construction may use explicitly declared Arch host tools, but exported target components must be distinguished from host inputs.

**Host qualification.** On the initial Arch Linux host, record architecture and kernel information, required build utilities and their executable versions, compiler/linker capability, and potentially contaminating build environment settings. Qualification shall separately establish (1) tool availability and working C/C++ compile/link probes, (2) compatibility with the chosen target interfaces, (3) the ability to execute the chosen isolation arrangement including mount and permission behavior, and (4) availability and verification of resolved upstream sources. Fail with actionable deficiencies; never install, upgrade or remove host packages. Minimum host/kernel versions shall be justified by observed compatibility results, not assumed from package presence or prototype constants.

**Source selection and restart identity.** Start each *new* bootstrap execution by qualifying the host and mapping required installed Arch package versions to corresponding upstream source releases; normalize distribution release suffixes and other differences explicitly. Record selected source identity, exact version, source URL, verification method, verified digest and any signature evidence in execution-local state. Once selection for that execution is established, subsequent steps and resumption must reuse those exact verified inputs and reject changed or inconsistent cached bytes; restarting with new host-derived selections is a **new** execution. No repository-maintained bootstrap-version catalog or enduring upstream-tracking policy is created.

**Isolation and target contract.** Select one initial target architecture, target triple, Linux ABI and GNU C library strategy as a *Planning* contract before dependent toolchain construction. The prototype's `x86_64-distro-linux-gnu` is evidence, not yet an accepted selection. Specify allowed read-only host tools/libraries and writable work/sysroot mounts, environment and UID requirements, host-dependent phase boundaries, and cleanup. Do not silently fall back to elevated or less-isolated execution if the selected arrangement is unavailable. Retain the actual host-versus-target dependency inventory for review; isolation alone does not establish host independence.

**Construction.** Build the target assembler/linker, initial compiler, Linux API headers, C library interface, and necessary compiler/runtime finalization in an explicit dependency order. Keep the toolchain installation root and target sysroot distinguishable; declare each intermediate host dependency and each input carried forward to M2. The cross-toolchain need not be made into a final Distro package in M1.

**Acceptance and M2 handoff.** Require fresh-workspace construction and inspect compiler driver configuration, target triple, search paths, generated ELF interpreters and dynamic-library closure. Run representative target C and C++ compile/link/execute probes in a suitable isolated target context, including a negative contamination case. Verify that observed dependencies match the declared intermediate foreign-host allowances and that M2 will use the intended target headers, linker and libc, rather than silently taking them from the Arch host. Record machine-readable qualification, selected source identities/digests, build input and environment, toolchain output inventory, probes, failures, and restart evidence. M2 begins only after these checks pass.

### M2 — Temporary tools

- Using the M1 toolchain, produce and validate target-executable temporary userspace with enough utilities, libraries, and native tools to enter and work within a distinct target root.
- Record dependency closure, interpreter/linker paths, and file provenance. Use isolated mount/input rules; foreign-host userspace must not silently appear as native output.
- Validate native execution and an actual representative native compile/build inside the temporary environment before M3 begins.

### M3 — Bootstrap-chroot Distro packages

- Produce a minimal Build toolchain and runtime collection as Distro package artifacts, following accepted package identity and package metadata semantics.
- Establish the minimal Build, Package Database publication, and Manage operations necessary to publish and consume that collection. Preserve one atomic generation and independent artifact integrity checks.
- Create a *fresh* definitive Build chroot by invoking Manage on the published artifacts. Do not copy temporary-root files into it except as explicitly accounted for within published packages.
- From that managed chroot, build and verify a representative Distro package without undeclared foreign-host userspace dependencies. Retain source, build, artifact, installed-closure, and execution evidence.

### M4 — Bootable package set

- Produce a Distro package collection including kernel, GRUB, systemd, essential userspace, runtime closure, and required Build/Manage tools and dependencies to create a managed Build chroot and build Distro packages.
- Ensure the *bootable environment itself* contains the applicable Build and Manage capabilities and access to the Distro-native package collection required to construct the Build chroot. A package set that merely boots is insufficient.
- Demonstrate, before M5, that the M4 collection supports creation of a fresh Build chroot and a native representative package build in an appropriate isolated system context. Preserve package identities and checksums for the M5 installation.

### M5 — Installed VM

- Use Install to prepare a disposable VM target and delegate package population to Manage; Install handles target-specific configuration and bootloader setup, not unpacking package artifacts independently.
- Boot through installed GRUB into the installed Linux kernel and systemd-managed userspace; verify isolation from foreign-host userspace.
- From inside the running VM, create a *new* definitive Build chroot using Manage and the M4-published packages, enter/use it through Build, and produce and validate a representative package artifact.
- Verify that all relevant operations complete without access to bootstrap-only paths or foreign-host userspace. A boot-only smoke test is not sufficient for FS-001 acceptance.

## Required cross-cutting engineering decisions at Planning review

The following decisions must be explicit before dependent Build work; avoid treating any prototype choice as already selected:

1. **Environment contract:** target architecture, host kernel/ABI constraints, sandbox mounts and UID mappings, and contamination-failure policy.
2. **Source trust:** source selection mapping, authenticity/checksum policy, exact per-execution locking, cache integrity, and resume behavior.
3. **Artifact format:** physical serialization of the established `name + version + architecture + revision` identity and installable payload, with checksum external to verified bytes.
4. **Package Database:** physical representation of atomic published generation, global requirement/version registry, architecture catalog, immutable artifact references, and artifact-before-metadata publication order.
5. **Bootstrap dependency closure:** native toolchain and runtime inventory needed for both Build chroot and M4 bootable set, with explicit relationships and ownership.
6. **Manage transaction substrate:** minimal correct target-root installation with checksum, path ownership, dependency checks and durable installed state; fail safely on partial application.
7. **VM/install target:** one specific first VM firmware/partition/filesystem configuration; general hardware support deferred, GRUB/systemd boot mandatory.
8. **Acceptance fixtures:** representative package build and reproducible positive and negative tests for each milestone.

These are currently **open Planning decisions**, not implied defaults. Resolve them in Planning before Build must rely on them; do not silently commit to Arch-derived recipe behavior, G1 database formats, tar layouts, or QEMU BIOS just because a prototype used them.

## Evidence and validation strategy

- For M1–M2, retain machine-readable input, source checksum, environment, stage, runtime linkage, isolation, and failure evidence.
- For M3–M4, retain published package identities and integrity, database generation, Manage-installed closure and file inventory, and successful independent builds.
- For M5, retain installer commands, selected VM target, installed package state, GRUB/systemd boot marker, and a verified package built from a freshly assembled chroot within the VM.
- Include negative checks for host contamination, modified source/artifact checksums, incomplete generation publication, ownership conflicts, invalid dependency closure, and inability to form an independent Build chroot.
- Bind each active mechanical requirement to concrete registered product Validation tasks during Build. A successful mechanical run does not replace semantic review.

## Prototype evidence, not design authority

`proto/distro-bootstrap-chroot` informs host qualification and staged toolchain work; `proto/lfs-optimize` informs native construction and validation; `proto/g1-chroot`, `proto/g1-bootable`, and `proto/g2-installer` inform package, boot and install proofs; `proto/builder-discovery` and `proto/maint-lifecycle` inform source/recipe discovery and correction; `proto/bootstrap-staging` informs early staging methods. Reuse compatible mechanisms selectively without inheriting superseded semantics.
