# FS-003 — Stage 1C Initial Native Package Production Normative Requirements

Evaluation classifications: **M** mechanical, **S** semantic, **B** both. All FS-003 requirements are active for evaluation. Mechanical contract gates run through canonical product Validation; qualified-host functional and independent-consumption evidence additionally require Semantic Review. Passing Validation does not itself constitute Acceptance.

### FS-003-NR-001 — Invocation and Stage Selection
**Classification: B**

Build shall support `distro-buildroot --root <rootdir> --cross-chroot <artifact>` through its existing entry point and select an explicit Stage 1C native package list rather than a separate Bootstrap engine.

### FS-003-NR-002 — Verified Stage 1B Input
**Classification: B**

Before restoration, Build shall require matching Stage 1B archive and completion metadata and verify required identity, target, mount contract, success evidence, size and SHA-256; missing, mismatched or unsafe input shall fail without producing package publication.

### FS-003-NR-003 — Safe Workspace Separation
**Classification: B**

Build shall safely restore the verified Stage 1B filesystem into a fresh temporary construction environment while keeping source/build work, package output staging and published artifacts separate from it and from the Stage 1B construction workspace.

### FS-003-NR-004 — Shared Source and Recipe Authority
**Classification: B**

The first package slice shall use the authoritative shared Sed manifest, exact Sed 4.10 source selection and SHA-256, and directly executed Stage 1C Bash recipe; the list and recipe shall not create independent dependency declarations or a package-specific Build interpreter.

### FS-003-NR-005 — Native Production Execution
**Classification: B**

The selected package shall be constructed by target-native processes in a fail-closed isolated environment using the same Build execution behavior intended for later production construction, without undeclared foreign-host executable or runtime-library dependencies; the bootstrap input provider shall not define a separate mode.

### FS-003-NR-006 — Independent Package Staging
**Classification: B**

The selected native package's installation output shall be captured in its own staging filesystem, independent of the imported Stage 1B root and other package payloads; Build shall reject installation that escapes the authorized staging destination or relies on sweeping inherited files into a package.

### FS-003-NR-007 — Fixed Identity and Relationships Handoff
**Classification: B**

Build shall supply Manage with one fixed selected package identity, the separate staged filesystem and manifest-derived selected install-relevant relationships. Manage shall verify and preserve them without reselecting identity or deriving dependencies from recipes or temporary filesystem content.

### FS-003-NR-008 — Standard Manage Creation
**Classification: B**

Manage's standard create operation shall produce an independently consumable package artifact containing target-root-relative payload and embedded identity, with an authoritative non-directory installed-path inventory, rejecting unsafe members and escaping filesystem paths.

### FS-003-NR-009 — Local Repository Publication
**Classification: B**

Manage's standard publish operation shall record the artifact's fixed identity, selected relationships, owned paths, location, size and integrity checksum in a local authoritative repository index, and shall not expose an index selection before its referenced artifact is complete and verified.

### FS-003-NR-010 — Ownership and Publication Failure Integrity
**Classification: B**

Package creation or publication shall fail on conflicting ownership, inconsistent identity, artifact integrity failure or incomplete output, and shall preserve any previously usable authoritative selection on failure.

### FS-003-NR-011 — Independent Artifact Verification
**Classification: B**

FS-003 shall demonstrate an independently verifiable package and repository record without access to the original Build workspace, including exact identity, dependency metadata, integrity, ownership inventory and safe payload extraction.

### FS-003-NR-012 — Qualified Native Functional Evidence
**Classification: B**

On a qualified host the selected package shall be built with target-native tools from the restored Stage 1B environment and its representative installed executable verified there without undeclared host userspace dependencies.

### FS-003-NR-013 — Mechanical Traceability
**Classification: M**

Every active FS-003 requirement classified M or B shall have exact bindings to registered required product mechanical-validation tasks, and canonical Validation shall fail when an applicable required task fails.

### FS-003-NR-014 — Scope and Component Boundaries
**Classification: S**

FS-003 shall remain one initial Build-to-Manage native package slice using the accepted shared production mechanisms. It shall not claim a complete `distro-buildroot` closure, install packages into a managed production root, implement Stage 2 or final self-replication, or introduce a parallel package format, engine or publisher.

### FS-003-NR-015 — Semantic Review and Acceptance
**Classification: S**

FS-003 shall undergo Semantic Review against the exact selected accepted Design and reviewed Planning result; mechanical validation or publication of a development branch alone shall not constitute Acceptance, which requires intentional integration into `main`.
