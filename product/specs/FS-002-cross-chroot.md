# FS-002 — Cross-Chroot Temporary Tools Normative Requirements

Evaluation classifications: **M** mechanical; **S** semantic; **B** both. All FS-002 requirements are active for evaluation. Classification is retained independently of state. Mechanical contract checks exercise implementation boundaries; qualified-host functional and relocation evidence also requires Semantic Review.

### FS-002-NR-001 — Stage 1B Invocation
**Classification: B**


`product/scripts/build` shall support `cross-chroot --root <rootdir> --cross-toolchain <artifact>`, selecting host-executed Stage 1B construction through the shared Build engine and a distinct cross-chroot package list.

### FS-002-NR-002 — Verified Input Handoff
**Classification: B**


Stage 1B shall require and validate the Stage 1A `cross-toolchain.tar.xz` and matching `cross-toolchain.json` completion metadata, including expected schema/identity, target and mount contract, successful verification claims, size, and SHA-256; it shall reject an archive without its valid matching metadata.

### FS-002-NR-003 — Workspace and Safe Import
**Classification: B**


Stage 1B shall use separate `build/`, `root/`, and `artifacts/` workspace roles, safely extract the verified Stage 1A filesystem into a fresh installed root, and shall not depend on Stage 1A's original build workspace or copy temporary construction work into its output artifact.

### FS-002-NR-004 — Shared Package Authority
**Classification: B**


Stage 1B shall use unique authoritative YAML package manifests from `product/src/build/packages/` for package identities, upstream source templates, verification schemes and dependencies, reusing the existing Binutils and GCC manifests; manifests shall not contain selected package versions or build instructions.

### FS-002-NR-005 — Exact Stage Selection
**Classification: B**


The distinct cross-chroot YAML list shall select exact versions, verification digests, ordered execution steps, supplementary verified source selections when needed, and Bash recipe paths without declaring its own package dependencies or construction instructions. Selected sources shall not silently float or substitute versions.

### FS-002-NR-006 — Direct Bash Execution
**Classification: B**


Build shall execute the selected user-maintained cross-chroot Bash recipes directly with the documented `DISTRO_*` source/build/root/toolchain/identity context; package-specific configure/build/install instructions shall reside in the recipes rather than a JSON interpreter or package-specific Build application dispatch.

### FS-002-NR-007 — Verified Source Handling and Dependency Availability
**Classification: B**


Build shall verify all selected upstream and supplemental source bytes before extraction or recipe execution, use deterministic prerequisite ordering, explicitly recognize prerequisite capabilities provided by the verified Stage 1A input, and reject missing or incompatible prerequisites.

### FS-002-NR-008 — Sandboxed Host Construction
**Classification: B**


Every Stage 1B construction recipe shall execute from the host in the existing fail-closed controlled sandbox with the target root mounted at a stable sandbox-visible installation path, sanitized environment, read-only host system access, and no network access; construction shall not write host system files or silently execute outside isolation.

### FS-002-NR-009 — Controlled Installation and Ownership
**Classification: B**


Stage 1B shall install only into its target filesystem and reject unintended collisions with imported or previously installed files. Any Binutils/GCC compiler-private transition, or GCC runtime/development-library transition under `/usr/lib` arising from the verified Stage 1A GCC handoff, shall require an explicitly bounded set of paths, verification of the prior imported content, and recorded identities of the staged replacements. A candidate assembled for review shall not supersede the imported root or become a published artifact until functional and relocation verification succeeds.

### FS-002-NR-010 — Functional Target-Native Tools
**Classification: B**


The Stage 1B result shall demonstrably execute its target-native shell and representative required utilities and compile, link, and execute minimal native C and C++ programs using target-root compiler, linker, loader and libraries without undeclared foreign-host userspace dependencies.

### FS-002-NR-011 — Portable Stage 1C Archive Handoff
**Classification: B**


On success, Stage 1B shall publish a filesystem-only `cross-chroot.tar.xz` and `cross-chroot.json` completion marker with artifact identity, size, SHA-256, parent Stage 1A artifact digest, source selections and successful functional/relocation verification evidence. The archive shall be checked after restoration in a distinct workspace without the original construction workspace available; metadata is published last.

### FS-002-NR-012 — Failure Integrity
**Classification: B**


Failure in selection, source verification, import, isolation, construction, installation, functional or relocation checks, or publication shall exit unsuccessfully and shall not expose a partial or stale Stage 1C handoff as complete.

### FS-002-NR-013 — Bootstrap and Scope Boundaries
**Classification: S**

FS-002 shall remain a Stage 1B operation of Build using the established engine. It shall not introduce an independent Bootstrap engine, implement Stage 1C package publication or isolated native production Build, perform native generation-to-generation self-replication, or implement Install or Manage merely as prerequisites.

### FS-002-NR-014 — Mechanical Traceability
**Classification: M**


Every active FS-002 requirement classified M or B shall have an exact binding to one or more registered required product mechanical-validation tasks, and canonical repository Validation shall fail when an applicable required task fails.

### FS-002-NR-015 — Semantic Review and Acceptance
**Classification: S**

FS-002 shall be evaluated semantically against the selected accepted Design and reviewed Planning result. Passing mechanical Validation alone shall not constitute Acceptance; Acceptance requires intentional integration of satisfactory candidate state into `main`.
