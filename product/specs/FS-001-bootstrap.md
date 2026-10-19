# FS-001 — Distro Bootstrap Normative Requirements

All requirements are **inactive** during Planning and carry no current implementation, mechanical-evaluation, or semantic-evaluation obligation. Build-stage activation requires Planning to change requirement state and Build to supply any required mechanical enforcement bindings. Classification: `M` mechanically evaluated, `S` semantically evaluated, `B` both. Mechanical task bindings are a **Build-stage deliverable** and are not fabricated by this Planning candidate.

### FS-001-NR-001 — Qualified Foreign Host

**Classification: B**

**State: Inactive**

Bootstrap shall qualify its initial Arch Linux host for the required construction capabilities and report missing or incompatible prerequisites without installing, removing, or modifying foreign-host packages.

### FS-001-NR-002 — Source Identity and Consistency

**Classification: B**

**State: Inactive**

Bootstrap shall select upstream source identities and versions from qualified host package versions, resolve distribution-specific version differences as necessary, and retain consistent verified source identities across one execution and its resumption without imposing a permanent repository-pinned bootstrap version catalog.

### FS-001-NR-003 — Cross-toolchain Result

**Classification: B**

**State: Inactive**

M1 shall produce and validate a Distro-targeting assembler/linker, compiler, Linux API headers, and C library interface sufficient to construct the next stage.

### FS-001-NR-004 — Cross-toolchain Isolation

**Classification: B**

**State: Inactive**

M1 validation shall establish compiler/linker target behavior and inspect generated runtime dependencies to detect undeclared foreign-host userspace reliance.

### FS-001-NR-005 — Temporary Native-Capable Environment

**Classification: B**

**State: Inactive**

M2 shall establish an isolated, native-capable temporary toolchain and userspace environment that can reproduce its complete required toolchain, runtime, utilities, and native build procedures into a fresh independent temporary root using build execution and orchestration available inside the producing environment. The reconstructed environment shall contain the complete native tools and procedures to repeat that replication (without requiring a generation-C build), without requiring undeclared foreign-host userspace or a foreign-host Python runner to execute or orchestrate its package builds.

### FS-001-NR-006 — Temporary/Definitive Boundary

**Classification: B**

**State: Inactive**

The temporary bootstrap chroot shall remain a construction environment and shall not be treated as an installed Distro system, the definitive Build chroot, or a source of untracked final-system files.

### FS-001-NR-007 — Native Bootstrap Packages

**Classification: B**

**State: Inactive**

M3 shall produce Distro-native package artifacts conforming to the accepted package identity, payload, runtime metadata, ownership, checksum and published package state contracts rather than introducing a second permanent package format or installed-package authority.

### FS-001-NR-008 — Managed Definitive Build Chroot

**Classification: B**

**State: Inactive**

M3 shall materialize its temporary construction chroot solely from the verified standalone M2 `tar.xz` development artifact, then assemble the definitive Build chroot as a fresh target using Manage and Distro-produced permanent package artifacts, without copying the temporary bootstrap root wholesale.

### FS-001-NR-009 — Independent M3 Package Build

**Classification: B**

**State: Inactive**

The definitive M3 Build chroot shall use Distro-native Build capabilities to rebuild and validate every package in the complete declared package, runtime and build-dependency closure required to constitute and operate that Build chroot, without undeclared foreign-host userspace, host-side package-build orchestration or bootstrap-only construction dependencies. M3 acceptance shall not require assembly of a second Build chroot.

### FS-001-NR-010 — Bootable Native Collection

**Classification: B**

**State: Inactive**

M4 shall use the M3 Distro-native Build environment to build or validly reuse and publish the complete declared bootable package manifest, including the Linux kernel, GRUB, systemd, essential userspace and all transitive runtime and build dependencies. Each newly built package shall use a fresh isolated Build root provisioned by Manage from verified published Distro packages with its declared build dependencies, and the authoritative repository shall provide integrity-checked published packages for reuse through Manage installation and durable resumption checkpoints, without an independent build-cache mechanism.

### FS-001-NR-011 — M4 Build Capability

**Classification: B**

**State: Inactive**

The complete M4 published collection shall include and make available the Distro-native Build and Manage capabilities and package dependency closure needed to create a new managed definitive Build chroot and build Distro packages after installation; mere bootability or a partial package manifest shall not satisfy M4. M4 shall validate complete coherent publication, cache reuse and failure resumption, while actual installed-VM boot and subsequent native Build-chroot creation are demonstrated in M5.

### FS-001-NR-012 — Install Delegation

**Classification: B**

**State: Inactive**

M5 installation shall use Install for target preparation and system-level configuration and delegate application of Distro package artifacts and installed package state to Manage, without a second package installer.

### FS-001-NR-013 — Installed VM Boot

**Classification: B**

**State: Inactive**

M5 shall install a virtual machine that boots through GRUB into the Distro Linux kernel and systemd-managed usable local userspace without depending on the foreign host's userspace.

### FS-001-NR-014 — Native Rebuild on Installed VM

**Classification: B**

**State: Inactive**

From within the independently booted M5 VM, Distro shall clone the `wiigelec/distro` repository and run its normal bootstrap workflow with the installed Distro system serving as the foreign host: qualify that host, freshly construct and validate the M1 cross-toolchain using its native host prerequisites, construct M2 from the new M1 handoff, and pass M2's complete generation-A-to-generation-B self-replication validation. The Distro-hosted bootstrap shall not require Arch-only package-management tools, the original Arch-hosted bootstrap outputs or workspaces, or undeclared external userspace or build orchestration. During construction through M2 self-replication, it shall use Bubblewrap to protect the installed host filesystem against accidental modification; after M2 has fully rebuilt itself, controlled native chroot execution requires no additional isolation mechanism. M5 acceptance completes when the independently booted VM has freshly rebuilt and validated M1 and its M2 generation A has completely constructed generation B; a separate installed-VM Build-chroot/package-build acceptance test is not required because native Build-chroot and package-closure capabilities are proven in M3/M4.

### FS-001-NR-015 — Publication Consistency

**Classification: B**

**State: Inactive**

Bootstrap publication used by Manage shall expose only coherent Package Database generations and shall make every newly referenced immutable artifact available before its generation becomes current.

### FS-001-NR-016 — Evidence and Validation

**Classification: B**

**State: Inactive**

FS-001 shall retain inspectable provenance, environment, source identities, package artifact identities/checksums, installed closure, and stage-specific positive and negative validation evidence sufficient to distinguish temporary foreign-host assistance from independent native output.

### FS-001-NR-017 — Native Lifecycle Transition

**Classification: S**

**State: Inactive**

Bootstrap shall establish the initial Distro package baseline without making host-derived source selection or temporary bootstrap construction state an ongoing package-update authority; subsequent normal package lifecycle policy shall retain the separately designed Package Manifest, Build State, and Package Database authorities.

### FS-001-NR-018 — Bounded Bootstrap Scope

**Classification: S**

**State: Inactive**

FS-001 shall implement only the Build, Manage, Install, and bootstrap capabilities necessary to establish and verify the required independent package-building and bootable environments, without prematurely treating prototype shortcuts or deferred product functionality as normative policy.
