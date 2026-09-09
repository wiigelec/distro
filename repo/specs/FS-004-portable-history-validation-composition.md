# FS-004 — Portable History and Validation Composition Normative Requirements

### FS-004-NR-001 — Root operational scripts role

**Classification: B**

The maintained repository-root boundary shall authorize `scripts/` only as a repository-wide operational composition role, and FS-004 shall authorize `scripts/validate` as its only maintained entry.

### FS-004-NR-002 — Repository-wide Validation entry point

**Classification: M**

The repository shall provide executable `scripts/validate` as the repository-wide mechanical Validation entry point.

### FS-004-NR-003 — Framework Validation ownership

**Classification: B**

Repository-wide Validation shall delegate framework mechanical Validation to `repo/scripts/validate` without moving or duplicating framework normative predicates into the root composition layer.

### FS-004-NR-004 — Product Validation composition

**Classification: B**

When the maintained `product/` ownership domain is present, repository-wide Validation shall require executable `product/scripts/validate`, execute it after successful framework Validation, and fail when product Validation is absent or fails. A product with no current mechanical obligations shall use its canonical empty-manifest Validation state rather than omit product Validation.

### FS-004-NR-005 — CI delegation

**Classification: B**

Active CI mechanical gating shall delegate to `./scripts/validate` and shall not independently select framework or product Validation implementations.

### FS-004-NR-006 — Portable Design revision representation

**Classification: B**

Each Functional Set shall retain exactly one well-formed 40-character lowercase `design_revision` identifier, and generic framework Validation shall not require that identifier's originating Git commit object to exist in the current repository merely to validate the retained Planning artifact.

### FS-004-NR-007 — Existing exact Design binding preservation

**Classification: B**

Where an existing normative requirement fixes a Functional Set to one exact Design revision value, framework Validation shall continue to enforce that exact value even though generic local-object resolution is not required.

### FS-004-NR-008 — Independent-history framework operation

**Classification: B**

Canonical framework mechanical Validation shall remain operable when a well-formed retained framework Planning `design_revision` refers to an originating commit object absent from the current repository.

### FS-004-NR-009 — Active documentation alignment

**Classification: B**

`README.md` and `AGENTS.md` shall describe repository-root Validation composition, domain Validation ownership, and the portable meaning of retained Design revision identifiers.

### FS-004-NR-012 — Minimal installed framework snapshot

**Classification: B**

When `repo/validation/framework-source.json` exists, `repo/planning/` may be absent. Canonical framework Validation shall not fail merely because framework-development Planning history is absent, shall skip Planning-history checks that require that directory, and shall continue mechanically evaluating the installed normative requirement state from `repo/specs/` and `repo/validation/requirement-evaluation.json`.

### FS-004-NR-010 — Composition does not own normative meaning

**Classification: S**

Repository-root operational composition shall not become a source of framework or product Design meaning, normative requirements, or domain implementation semantics.

### FS-004-NR-011 — No supplier-history machinery

**Classification: S**

FS-004 shall not require imported supplier ancestry, Git grafts, replace refs, bundles, hidden remotes, provenance databases, lineage systems, or generalized plugin machinery merely to preserve framework portability.

### FS-004-NR-013 — Canonical Product Validation Entry Point

**Classification: M**

When maintained `product/` exists, `product/scripts/validate` shall be executable and shall remain a narrow launcher that delegates product Validation execution to `product/validation/validate_product.py` while forwarding command arguments unchanged.

### FS-004-NR-014 — Product Requirement Evaluation Manifest Integrity

**Classification: M**

When maintained `product/` exists, `product/validation/requirement-evaluation.json` shall be a well-formed versioned Requirement Evaluation Manifest whose bindings reference existing active product normative requirements; every active product requirement classified `M` or `B` shall have exactly one binding to one or more unique validation tasks, while active `S` requirements and inactive requirements shall not have mechanical bindings.

### FS-004-NR-015 — Product Validation Task Resolution Interface

**Classification: M**

The canonical product Validation entry point shall provide a task-resolution interface that can enumerate available product validation task identities and execute one named task; every task referenced by the product Requirement Evaluation Manifest shall resolve through that interface, and unknown task identities shall fail.

### FS-004-NR-016 — Product Validation Gate

**Classification: M**

Invoking canonical product Validation without selecting a task shall execute the distinct validation tasks required by the active product Requirement Evaluation Manifest and shall fail when any required product validation task fails; an empty valid manifest shall succeed without inventing a product predicate.

### FS-004-NR-017 — Product Predicate Ownership

**Classification: S**

Framework Validation may enforce product Validation structure, manifest integrity, classification coverage, and task identity resolution, but shall not own or execute product-specific normative predicates merely to perform those generic framework checks.
