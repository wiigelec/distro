# FS-004 — Stage 1C Native Buildroot Completion Normative Requirements

Evaluation classifications: **M** mechanical, **S** semantic, **B** both. All requirements are **State: Inactive** during initial Planning; activation requires corresponding Build-owned registered mechanical checks and exact bindings in `product/validation/requirement-evaluation.json`. An inactive requirement is not accepted or satisfied. Semantic Review and intentional integration are separate from mechanical Validation.

### FS-004-NR-001 — Complete Explicit Selection
**Classification: B**
**State: Inactive**

Build shall select a reviewed, pinned native package collection sufficient for the selected representative production workload, using version and source-verification selections from the Stage 1C list and authoritative package manifests for source/dependency meaning.

### FS-004-NR-002 — Dependency Categories and Deterministic Closure
**Classification: B**
**State: Inactive**

Build shall resolve exact selected package relationships and a deterministic construction order from authoritative manifest dependency categories, rejecting absent, ambiguous, cyclic and inconsistent selections. Imported Stage 1B capabilities may satisfy verified bootstrap construction prerequisites but shall not satisfy final installed-package relationships; construction and installed dependency graphs shall each be validated separately. Install-relevant relationships shall not be inferred from recipes or ELF inspection.

### FS-004-NR-003 — Verified Bootstrap Input
**Classification: B**
**State: Inactive**

Initial Stage 1C construction shall consume and safely restore only the verified Stage 1B handoff, preserving the existing identity, integrity, relocation and isolation gates, without depending on its original construction workspace.

### FS-004-NR-004 — Shared Native Execution
**Classification: B**
**State: Inactive**

All selected packages shall execute directly selected native Bash recipes through the common fail-closed target-native Build path with no undeclared foreign-host executable or runtime-library dependencies; changing the root provider shall not change the construction engine.

### FS-004-NR-005 — Independent Package Staging
**Classification: B**
**State: Inactive**

Each selected package shall have an isolated installation staging filesystem and fixed Build-selected identity and relationships; imported Stage 1B contents and other package outputs shall not be swept into its payload.

### FS-004-NR-006 — Manage-Owned Package Creation and Publication
**Classification: B**
**State: Inactive**

Build shall delegate package creation and publication to standard Manage operations; Manage shall verify immutable identity, selected relationships, artifact integrity and non-directory ownership without interpreting recipes or selecting dependencies.

### FS-004-NR-007 — Metapackage and Empty Payload
**Classification: B**
**State: Inactive**

Manage shall support an independently verifiable, payload-free `distro-buildroot` metapackage using the common package format and authoritative manifest-derived selected relationships, without weakening ordinary payload safety checks.

### FS-004-NR-008 — Filesystem Layout and Ownership
**Classification: B**
**State: Inactive**

Build shall construct and independently stage a verifiable Distro-owned `filesystem` package with the selected directories, modes and merged-/usr links. Manage shall create, publish, verify and install it through standard operations before dependent payloads under manifest-derived relationships. Compatible shared directories are permitted, non-directory paths have exclusive owners, and conflicting modes, traversal, unsafe links, unsupported members and target-root escapes shall be rejected.

### FS-004-NR-009 — Dependency Resolution from Repository
**Classification: B**
**State: Inactive**

Manage shall resolve an exact, closed installable `distro-buildroot` selection from authoritative repository records, validating all referenced identity, dependency, size, checksum and payload metadata before installation.

### FS-004-NR-010 — Fresh Managed Installation and Installed State
**Classification: B**
**State: Inactive**

Manage shall safely install the resolved closure into a fresh target root and durably record installed identities, relationships, artifact integrity and owned paths in a Manage-owned installed-state database distinct from the package repository index; a partial failure shall not be reported as a completed installation.

### FS-004-NR-011 — Coherent Collection Publication
**Classification: B**
**State: Inactive**

Incomplete or unverified package selections shall not be advertised as a complete selectable `distro-buildroot`; coherent promotion shall occur only after candidate-collection verification and shall preserve any previously usable authoritative selection on failure.

### FS-004-NR-012 — Production Root Provider Integration
**Classification: B**
**State: Inactive**

Normal Build shall consume a Manage-installed package-derived root through the same native recipe execution mode used for Bootstrap, without replacing it with a special Stage 1C-only root assembler.

### FS-004-NR-013 — Independent Managed-Root Functional Proof
**Classification: B**
**State: Inactive**

On a qualified host, a fresh root installed independently from published package artifacts, without the original Stage 1B or Build workspaces, shall execute a representative native package build through ordinary Build, and the staged and published result shall be functionally and structurally verified. Its verification publication shall preserve the immutable identity and artifact selection of the initial Sed package and shall verify actual native executable-interpreter and loader closure under the installed filesystem layout.

### FS-004-NR-014 — Negative and Interruption Integrity
**Classification: B**
**State: Inactive**

Required tests shall reject missing/corrupt packages, dependency conflicts/cycles, unsafe archive and link paths, ownership collisions, host-userspace exposure and incomplete installation/publication; interrupted operations shall not advertise an invalid complete collection.

### FS-004-NR-015 — Mechanical Traceability
**Classification: M**
**State: Inactive**

Every active mechanically classified FS-004 requirement shall bind exactly to registered required product validation tasks, and canonical Validation shall fail when any required applicable task fails.

### FS-004-NR-016 — Architectural Scope
**Classification: S**
**State: Inactive**

FS-004 shall complete DP-006 Stage 1C without claiming Stage 2, bootable installation or final generation-to-generation self-replication; it shall preserve Design component boundaries and use no parallel engine, package format or publisher.

### FS-004-NR-017 — Semantic Review and Acceptance
**Classification: S**
**State: Inactive**

FS-004 shall undergo Semantic Review against its exact selected Design revision, complete Planning and qualified-host evidence; mechanical validation alone shall not constitute Acceptance, which requires intentional integration into `main`.
