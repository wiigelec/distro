---
functional_set: FS-001
artifact: normative-specification
title: Framework Lifecycle Substrate Specification
---

# FS-001 — Normative Specification

Evaluation classifications:

- **M** — mechanical
- **S** — semantic
- **B** — both mechanical and semantic

## Requirements

### FS-001-NR-001 — Canonical Design

**Classification: B**

The canonical active Design corpus shall remain human-readable Markdown under `repo/design/`.

### FS-001-NR-002 — Exact Design Binding

**Classification: M**

FS-001 Planning shall identify exact Design revision `36735bd44e47b70f97221d61033e2affca9b9616`.

### FS-001-NR-003 — Planning Artifact Separation

**Classification: M**

FS-001 shall retain separate durable artifacts for Functional Set scope, Plan, and normative requirements.

### FS-001-NR-004 — Planning History

**Classification: S**

Accepted Functional Set Planning artifacts shall remain durable repository history and shall not be treated as Design merely because they persist.

### FS-001-NR-005 — Requirement Identity

**Classification: M**

Each FS-001 normative requirement shall have a unique identity of the form `FS-001-NR-NNN`.

### FS-001-NR-006 — Evaluation Classification

**Classification: M**

Every FS-001 normative requirement shall be explicitly classified as mechanical, semantic, or both.

### FS-001-NR-007 — Design Fidelity

**Classification: S**

FS-001 normative requirements and technical realization shall preserve the meaning of the selected Design without introducing a new Governance, Conformance, Assurance, authority, provenance, evidence, or adjudication architecture not required by that Design.

### FS-001-NR-008 — Historical State Non-Authority

**Classification: S**

Implementation behavior shall not independently determine FS-001 normative obligations.

### FS-001-NR-009 — Requirement Evaluation Manifest

**Classification: B**

The accepted repository shall contain a durable Requirement Evaluation Manifest that directly identifies the currently applicable mechanical normative requirement-to-Validation-task bindings.

### FS-001-NR-010 — Manifest Non-Authority

**Classification: S**

The Requirement Evaluation Manifest shall represent mechanical enforcement bindings only and shall not independently create, amend, or replace normative requirements.

### FS-001-NR-011 — Bidirectional Mechanical Traceability

**Classification: B**

For every mechanically enforced normative requirement applicable to FS-001, it shall be possible to determine which Validation task or tasks enforce it, and for every normative Validation task introduced by FS-001, it shall be possible to determine which normative requirement or requirements justify it.

### FS-001-NR-012 — Mechanical Binding Completeness

**Classification: M**

Every FS-001 normative requirement classified as mechanical shall have at least one exact Validation-task binding before Acceptance. Every requirement classified as both shall have at least one exact Validation-task binding for its mechanically decidable portion before Acceptance.

### FS-001-NR-013 — Semantic Evaluation Boundary

**Classification: S**

FS-001 shall not introduce artificial mechanical predicates solely to claim mechanical evaluation of obligations whose relevant meaning cannot be reliably mechanically decided.

### FS-001-NR-014 — Canonical Validation Entry Point

**Classification: M**

The active repository shall provide `repo/scripts/validate` as the canonical entry point for required mechanical Validation.

### FS-001-NR-015 — Required Validation Execution

**Classification: M**

`repo/scripts/validate` shall execute all required mechanical Validation tasks applicable to the candidate and shall return failure when any required task fails.

### FS-001-NR-016 — Validation Non-Authority

**Classification: S**

Validation tasks and their observed behavior shall not independently create or alter Design meaning or normative requirements.

### FS-001-NR-017 — Project-Native Validation

**Classification: S**

Mechanical Validation shall use the simplest reliable project-native mechanisms adequate to enforce the applicable obligation and shall not introduce generalized framework machinery without a demonstrated need.

### FS-001-NR-018 — README Lifecycle Alignment

**Classification: B**

`README.md` shall describe the active framework using the Design, Planning, Build, Validation, Semantic Review, and Acceptance lifecycle and shall not present the retired Governance / Conformance / Assurance architecture as current.

### FS-001-NR-019 — Agent Guidance Alignment

**Classification: B**

`AGENTS.md` shall route semantic defects to Design, Planning defects to Planning, and implementation or mechanical-enforcement-construction defects to Build, and shall not direct agents to infer normative intent from implementation behavior.

### FS-001-NR-020 — CI Delegation

**Classification: M**

Active CI mechanical gating shall invoke the canonical repository Validation entry point rather than define a separate set of normative mechanical predicates.

### FS-001-NR-021 — Conformance Workflow Retirement

**Classification: B**

The former `fs0-conformance` workflow and terminology shall not remain an active representation of the redesigned framework.

### FS-001-NR-022 — Functional Set Scope

**Classification: S**

FS-001 implementation shall remain limited to the minimal lifecycle substrate necessary for subsequent Functional Sets and shall not recreate capabilities solely because equivalent mechanisms existed in the former framework.

### FS-001-NR-023 — Build Implementation Freedom

**Classification: S**

Build may make ordinary code-level implementation decisions not prescribed by the Plan when those decisions preserve Design meaning, Plan intent, normative requirements, and Functional Set scope.

### FS-001-NR-024 — Mechanical Enforcement Ownership

**Classification: S**

Build shall construct mechanical enforcement and exact requirement bindings; Planning shall not be treated as having specified concrete Validation tasks merely by classifying a requirement for mechanical evaluation.

### FS-001-NR-025 — Semantic Review

**Classification: S**

Build Review shall evaluate the realized FS-001 repository state against both the complete FS-001 Planning result and the selected Design, including semantic fidelity, scope, omissions, unintended additions, and unnecessary complexity.

### FS-001-NR-026 — Validation Gate

**Classification: M**

All required mechanical Validation applicable to the FS-001 candidate shall pass before the candidate is eligible for Acceptance.

### FS-001-NR-027 — Review Gate

**Classification: S**

Required FS-001 Semantic Review shall converge with no unresolved material discrepancy before the candidate is eligible for Acceptance.

### FS-001-NR-028 — Acceptance

**Classification: S**

FS-001 Acceptance shall be represented by intentional integration of the satisfactory development candidate into `main`; no parallel acceptance artifact shall be required.
