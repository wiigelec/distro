# FS-002 — Complete Operational Lifecycle

### FS-002-NR-001 — Current Functional Set Discovery

**Classification: B**

Canonical Validation shall derive the current Functional Set set directly from canonical Planning and normative-specification surfaces rather than from FS-001-specific constants or a separately maintained Functional Set registry.

### FS-002-NR-002 — Planning and Specification Correspondence

**Classification: M**

Every discovered current Functional Set shall have exactly one canonical Planning directory containing `functional-set.md` and `plan.md` and exactly one corresponding normative specification under `repo/specs/`.

### FS-002-NR-003 — Functional Set Identity Consistency

**Classification: M**

A Functional Set's `FS-NNN` identity shall agree across its Planning directory, `functional-set.md`, normative specification, and normative requirement identity prefixes.

### FS-002-NR-004 — Exact Design Revision Form

**Classification: M**

Every discovered Functional Set shall declare a `design_revision` as a 40-character lowercase Git SHA that resolves to a Git commit in the repository.

### FS-002-NR-005 — Generic Normative Requirement Parsing

**Classification: M**

Canonical Validation shall parse normative requirements for every discovered Functional Set without requiring a per-Functional-Set parser or requirement-count constant.

### FS-002-NR-006 — Normative Requirement Identity

**Classification: M**

Every current normative requirement shall have a unique identity of the form `FS-NNN-NR-NNN` whose Functional Set prefix matches its owning specification.

### FS-002-NR-007 — Evaluation Classification and Requirement State

**Classification: M**

Every current normative requirement shall record exactly one evaluation classification encoded as `M`, `S`, or `B`. A normative requirement shall be active by default and may be marked `Inactive` separately from its evaluation classification.

### FS-002-NR-008 — Current Requirement State and Mechanical Applicability

**Classification: B**

A normative requirement marked `**State: Inactive**` in its canonical specification shall remain defined but shall have no current implementation, mechanical-evaluation, or semantic-evaluation obligation and no Requirement Evaluation Manifest binding. A requirement without that marker is active. Every active requirement classified `M` or `B` shall have a Requirement Evaluation Manifest binding for its mechanically decidable portion, while active requirements classified `S` shall have no manifest binding.

### FS-002-NR-009 — Manifest Requirement Resolution

**Classification: M**

Every Requirement Evaluation Manifest requirement reference shall resolve to exactly one discovered normative requirement classified `M` or `B`, and duplicate bindings for the same requirement shall be rejected.

### FS-002-NR-010 — Validation Task Resolution

**Classification: M**

Every Validation task referenced by the Requirement Evaluation Manifest shall resolve to a registered required project-native Validation task.

### FS-002-NR-011 — Mechanical Enforcement Justification

**Classification: B**

Every registered required Validation task shall remain justified by at least one currently applicable mechanically evaluated normative requirement represented in the Requirement Evaluation Manifest.

### FS-002-NR-012 — Subsequent Functional Set Participation

**Classification: M**

Adding a conforming later Functional Set shall not require changing lifecycle validator source merely to add that Functional Set's identity, Planning path, specification path, requirement parser, or requirement count.

### FS-002-NR-013 — Canonical Validation Entry Point

**Classification: M**

`repo/scripts/validate` shall remain the canonical mechanical Validation entry point and shall execute all registered required Validation tasks applicable to current repository state.

### FS-002-NR-014 — Required Validation Failure Propagation

**Classification: M**

Canonical Validation shall fail when any registered required Validation task selected for the candidate fails and shall succeed only when all such required tasks pass.

### FS-002-NR-015 — CI Delegation

**Classification: M**

CI shall continue to delegate required lifecycle mechanical gating to `repo/scripts/validate` without maintaining an independent Functional Set list, requirement list, or independent normative predicates.

### FS-002-NR-016 — FS-001 Continuity

**Classification: B**

The completed operational lifecycle shall continue to discover, parse, bind, and validate FS-001 without changing or bypassing its accepted normative meaning.

### FS-002-NR-017 — Semantic Evaluation Boundary

**Classification: S**

Generic Functional Set discovery and requirement parsing shall not cause semantic-only requirements to be treated as mechanically decidable.

### FS-002-NR-018 — Historical State Non-Authority

**Classification: S**

Lifecycle mechanisms shall not treat repository history as current normative authority merely because that history is inspectable.

### FS-002-NR-019 — Registry Non-Requirement

**Classification: S**

FS-002 shall not introduce a Functional Set authority registry, lifecycle database, provenance database, correspondence graph, evidence store, adjudication system, or parallel acceptance record merely to complete lifecycle operation.

### FS-002-NR-020 — Project-Native Simplicity

**Classification: S**

The implementation shall remain the smallest practicable project-native mechanism that completes the current lifecycle without introducing a generalized validation or plugin framework.

### FS-002-NR-021 — Operational Documentation Fidelity

**Classification: B**

Active repository documentation and agent guidance shall remain consistent with the completed operational lifecycle and shall not introduce a second source of normative Planning meaning.

### FS-002-NR-022 — Framework Completion

**Classification: S**

Acceptance of FS-002 shall complete the lifecycle framework for the current Design unless later real use exposes a concrete missing or defective lifecycle capability requiring upstream correction.
