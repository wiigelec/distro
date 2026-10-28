# FS-001 — Cross-Toolchain Construction Normative Requirements

Evaluation classifications: **M** mechanical; **S** semantic; **B** both. Requirements are active unless marked inactive.

### FS-001-NR-001 — Stage 1A Invocation

**Classification: B**

**State: Inactive**

`product/scripts/build` shall support `cross-toolchain --root <rootdir>`, selecting the Stage 1A package list and host execution through the shared Build engine.

### FS-001-NR-002 — Bootstrap Ownership

**Classification: S**

**State: Inactive**

Stage 1A shall remain an operation of Build, implemented under the established Build/Bootstrap ownership, without introducing a separate permanent Bootstrap component or independent package-building engine.

### FS-001-NR-003 — Workspace Separation

**Classification: B**

**State: Inactive**

The selected Bootstrap workspace shall use `build/` for extraction and compilation, `root/` for the installed `/` filesystem, and `artifacts/` for the archived installed filesystem. Temporary build work shall not be part of the delivered filesystem archive.

### FS-001-NR-004 — Authoritative Manifests

**Classification: B**

**State: Inactive**

Package identity, upstream archive references, verification information and dependency declarations shall come from user-maintained YAML manifests in `product/src/build/packages/`, with exactly one authoritative manifest per selected package. Manifests shall not select versions or contain build instructions.

### FS-001-NR-005 — Exact List Selections

**Classification: B**

**State: Inactive**

The user-maintained YAML `cross-toolchain` list shall select explicit versions and Bash recipes for the selected packages and supply any required dependency version selections without redefining package dependency declarations or embedding construction commands.

### FS-001-NR-006 — Direct Bash Recipes

**Classification: B**

**State: Inactive**

Build shall directly execute the selected user-maintained Bash recipes under `product/src/build/recipes/`. Package-specific configure, compile, patch and installation instructions shall remain in those recipes, not in Build application code or an interpreted/generated recipe language.

### FS-001-NR-007 — Recipe Execution Context

**Classification: B**

**State: Inactive**

Build shall provide the documented source, build, installation-root, version/identity and target context required by selected recipes, and those recipes shall be independently executable when supplied with that context.

### FS-001-NR-008 — Source Selection and Verification

**Classification: B**

**State: Inactive**

Build shall resolve upstream release archives using the explicitly selected versions, acquire and verify sources according to the authoritative manifests before construction, and reject a selected source when its required verification fails. Stage 1A shall not discover or silently substitute a different upstream version.

### FS-001-NR-009 — Requirements and Ordering

**Classification: B**

**State: Inactive**

Stage 1A shall honor the relevant manifest-defined requirements and provide a deterministic construction order that makes needed prerequisites available before dependent recipes execute; missing or unsatisfiable required selections shall fail rather than be silently invented.

### FS-001-NR-010 — Installed Root Isolation

**Classification: B**

**State: Inactive**

Stage 1A shall install constructed target filesystem contents beneath `<rootdir>/root/` rather than into the foreign host's system filesystem. Any expected reliance on foreign-host tools during host execution shall remain explicit.

### FS-001-NR-011 — Usable Initial Cross-Toolchain

**Classification: B**

**State: Inactive**

The completed Stage 1A result shall provide the target assembler/linker, initial compiler and target header/C-library interface capabilities selected as necessary for the subsequent cross-chroot construction, and shall be demonstrated usable by relevant compile/link and target-artifact checks without requiring implementation of Stage 1B.

### FS-001-NR-012 — Archive Handoff

**Classification: B**

**State: Inactive**

On success, Stage 1A shall create in `<rootdir>/artifacts/` an independently usable archive of the installed `<rootdir>/root/` filesystem, preserving the filesystem semantics needed for Stage 1B and excluding temporary construction work.

### FS-001-NR-013 — Failure Integrity

**Classification: B**

**State: Inactive**

A failed source verification, package construction, installation, functional check or archive export shall fail the Stage 1A command and shall not report a partial or stale archive as a successful Stage 1B handoff.

### FS-001-NR-014 — Scope Exclusions

**Classification: S**

**State: Inactive**

FS-001 shall not implement Stage 1B/1C, managed package creation/publication, general isolated-buildroot execution, native system installation or the final Bootstrap self-replication proof merely as prerequisites of cross-toolchain construction.

### FS-001-NR-015 — Mechanical Traceability and Gate

**Classification: M**

**State: Inactive**

Every active FS-001 requirement classified `M` or `B` shall have an exact binding to one or more registered required product validation tasks, and canonical repository validation shall fail when a required mechanically decidable task fails.

### FS-001-NR-016 — Semantic Fidelity and Acceptance

**Classification: S**

**State: Inactive**

FS-001 shall remain subject to semantic review against the selected accepted Design and complete Planning result; mechanical validation passing shall not independently constitute Acceptance, which requires intentional integration of a satisfactory candidate into `main`.

### FS-001-NR-017 — Sandboxed Host Construction

**Classification: B**

**State: Inactive**

Every FS-001 package construction recipe shall execute inside the required controlled host sandbox, using only declared writable staging locations; if the sandbox cannot be established, Stage 1A shall fail without running the recipe unrestricted. Host system files shall not be writable by construction recipes.

### FS-001-NR-018 — Controlled Host Environment and Paths

**Classification: B**

**State: Inactive**

Stage 1A shall explicitly control the sandbox execution environment, host resource visibility, executable search paths, installation paths, and toolchain target/sysroot paths so that inherited host variables, host system libraries, and absolute host workspace locations do not silently control target construction.

### FS-001-NR-019 — Cross-Workspace Handoff Portability

**Classification: B**

**State: Inactive**

The Stage 1A filesystem archive shall be functionally usable after restoration into a different absolute host workspace, using a stable sandbox-visible installed filesystem location without relying on the original construction workspace. This shall be demonstrated by target compilation and linking against the restored toolchain and target interfaces with the original workspace unavailable.
