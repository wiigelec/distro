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

**Result and boundary.** M2 delivers a temporary, Distro-native-capable build environment that can **reproduce its entire required temporary toolchain and userspace closure**. It is not the definitive managed Build chroot or an installed Distro system. M2's first generation may use the validated M1 cross-toolchain and explicitly declared foreign-host assistance; M2 acceptance is based on native self-replication, not on the ability to execute a shell or compile one sample program.

**First-generation construction.** Import the verified M1 handoff and construct generation A in a distinct temporary root, keeping installed files separate from sources, workspaces, scripts, logs and completion records. Select the complete native shell, compiler, assembler/linker, build utilities, headers, libraries, and other capabilities needed to reproduce the M2 environment and support M3. Derive source identities from the current bootstrap execution's verified inputs rather than hardcoded prototype version pins. Declare all foreign-host tools and permitted intermediate construction dependencies.

**Native execution authority.** Generation A must possess and execute the tools and build procedures that construct its packages. The prototype's host-side Python runner, including any per-package injected Bash scripts, may help create generation A, but **may not be required to orchestrate or execute generation A's self-replication into generation B**. Package-specific build execution, sequencing, installation into the fresh target, and checks needed for replication must be driven using native capabilities available inside generation A. The foreign host may supply its kernel and controlled execution/mount interfaces, plus verified read-only source inputs, but not undeclared host executables, libraries, package-building logic, or Python-driven package dispatch.

**Self-replication proof.** Using generation A, construct a fresh and independently identifiable generation B from the verified source inputs and the declared M2 build instructions. Reproduce the **complete** required M2 toolchain, runtime, utilities, and native build procedures, not a representative subset; record component and dependency inventories for both generations. Confirm generation B operates its own compiler, linker, shell, build tools and supporting libraries in isolation, and can itself execute the same replication procedure (a repeatability proof; byte-identical binaries are not required). Inspect executable interpreters, search paths, dynamic libraries, installed files, and mount/input provenance for undeclared foreign-host userspace or copied-in bootstrap-only outputs.

**Failure and resumption.** Verify imported artifacts and source digests, detect incomplete extraction or installation, and never treat stamps or partially populated target roots as proof of completion. On resume, reuse consistent execution-local inputs and validated outputs or fail closed with explicit recovery instructions. Preserve independent generation-A and generation-B evidence, including package-specific commands/procedures actually run inside the native environment.

**Acceptance and M3 handoff.** M2 passes only when the full A-to-B self-replication completes from a fresh target, the reconstructed generation B is functionally complete and independent of foreign-host build tools or orchestration, and generation B can drive another equivalent replication. Retain machine-readable source, recipe, installed-closure, runtime-dependency, isolation, negative-contamination, failure, restart and cold-rebuild evidence. M3 consumes this self-hosting temporary environment to produce the first proper Distro package artifacts; M2 does not substitute its temporary installation state for Manage's eventual authoritative state.

### M3 — Bootstrap-chroot Distro packages

**Result and boundary.** M3 replaces temporary bootstrap construction with a definitive, managed Distro Build chroot whose complete required package closure can be rebuilt using Distro-native Build capabilities. The M2 temporary environment remains a construction input only, not an installed-package authority or source of untracked final files. M3 requires **one** fresh managed Build chroot and a full native rebuild of its own package closure; it does **not** require constructing a second Build chroot.

**Initial package production.** Use the validated, self-replicating M2 environment to build the first Distro-native toolchain, userspace, libraries and Build/Manage support packages. Build produces artifacts carrying the accepted `name + version + architecture + revision` identity and installable payload. Runtime relationships, ownership and whole-artifact checksums are produced for publication under the existing metadata and Package Database contracts; Manage does not consume Build recipes or temporary-root stamps as package authority. Resolve and record the complete package, runtime and build-dependency closure needed to reproduce the definitive Build chroot.

**Publication and integrity.** Establish the minimum Distro Build publication path, immutable artifact storage, coherent Package Database generation and repository interface needed by Manage. Publish referenced artifacts before making their metadata generation current. The generation includes the global requirement/version registry and applicable architecture catalog, and contains immutable artifact references, external whole-artifact checksums and authoritative runtime metadata. Reject incomplete, inconsistent or unverified publication and preserve prior valid generations.

**Managed Build-chroot construction.** Use Manage against a fresh empty target root to select the initial published collection, resolve its complete runtime dependencies and required providers, verify artifact identities and checksums, detect ownership and relationship conflicts, and install files and authoritative installed-package records. Record exact applied artifact checksums, package identities, install reasons, hold state and owned paths. Build owns build dependency intent and execution; Manage owns target-root package operations. Never copy the M2 root wholesale or import untracked bootstrap files. Specify safe failure and resumption behavior for partial application and installed-state commits.

**Complete native package reproduction.** Enter the managed Build chroot and use its Distro-native Build execution and orchestration to rebuild **every package necessary to constitute and operate that Build chroot**, including its compiler, assembler/linker, headers, runtime libraries, utilities, Build/Manage tools and required build-dependency closure. Define a finite, explicit authoritative inventory of that closure before testing, with evidence of every package's source, recipe, build dependencies, runtime dependencies and produced artifact. All package-specific build procedures execute using tools and dependencies available inside the managed environment, not Arch executables, host Python dispatch, M2 binaries or temporary construction-state shortcuts. Validate each rebuilt Distro package artifact against its expected identity, payload, metadata and integrity contracts. Newly rebuilt packages need not be installed into a second chroot or republished merely to pass M3; the initial collection must already have been published and used successfully by Manage.

**Acceptance and M4 handoff.** M3 passes only when Manage has assembled the definitive Build chroot from the initial published Distro packages and that chroot independently produces and validates the entire declared package closure required for its own operation. A representative package build alone is insufficient, but reconstructing a second Build chroot is unnecessary. Record the initial and rebuilt package inventories, published generation, source/recipe provenance, native build commands, artifact verification, installed-state integrity, runtime dependency closure, host-contamination checks and negative tests for checksum mismatch, dependency/ownership conflicts and interrupted operations. M4 consumes these proven Build, Manage and publication capabilities to construct a bootable package collection that retains native Build-chroot creation and package-building capability.

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
8. **Acceptance fixtures:** M2 full temporary-environment replication, M3 complete managed Build-chroot package-closure reproduction, and milestone-appropriate native build and reproducible positive/negative tests for M4–M5.

These are currently **open Planning decisions**, not implied defaults. Resolve them in Planning before Build must rely on them; do not silently commit to Arch-derived recipe behavior, G1 database formats, tar layouts, or QEMU BIOS just because a prototype used them.

## Evidence and validation strategy

- For M1–M2, retain machine-readable input, source checksum, environment, stage, runtime linkage, isolation, and failure evidence.
- For M3–M4, retain published package identities and integrity, database generation, Manage-installed closure and file inventory, and successful independent builds.
- For M5, retain installer commands, selected VM target, installed package state, GRUB/systemd boot marker, and a verified package built from a freshly assembled chroot within the VM.
- Include negative checks for host contamination, modified source/artifact checksums, incomplete generation publication, ownership conflicts, invalid dependency closure, and inability to form an independent Build chroot.
- Bind each active mechanical requirement to concrete registered product Validation tasks during Build. A successful mechanical run does not replace semantic review.

## Prototype evidence, not design authority

`proto/distro-bootstrap-chroot` informs host qualification and staged toolchain work; `proto/lfs-optimize` informs native construction and validation; `proto/g1-chroot`, `proto/g1-bootable`, and `proto/g2-installer` inform package, boot and install proofs; `proto/builder-discovery` and `proto/maint-lifecycle` inform source/recipe discovery and correction; `proto/bootstrap-staging` informs early staging methods. Reuse compatible mechanisms selectively without inheriting superseded semantics.
