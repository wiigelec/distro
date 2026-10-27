# FS-003 — Repository Ownership and Structural Boundaries

### FS-003-NR-001 — Repository and Product Ownership Separation

**Classification: B**

Maintained reusable repository/framework state shall remain owned by `repo/`, while maintained product-owned state shall remain owned by the generic `product/` domain, subject to explicitly authorized repository-root operational surfaces.

### FS-003-NR-002 — Generic Product Domain

**Classification: S**

The framework's `product/` ownership domain shall remain generic and shall not encode the repo-spec initializer or any other specific product's identity, semantics, technology, architecture, or feature set.

### FS-003-NR-003 — Closed Maintained Root Boundary

**Classification: M**

Maintained repository-root entries shall be limited to the authorized directory roles `.github/`, `repo/`, `product/`, and `user/` and the authorized file roles `.gitignore`, `AGENTS.md`, `LICENSE`, and `README.md`; absence of an authorized optional role is permitted, while an additional maintained root role is not.

### FS-003-NR-004 — Closed `repo/` Boundary

**Classification: M**

Maintained direct children of `repo/` shall be directories whose roles are limited to `design/`, `planning/`, `scripts/`, `specs/`, `src/`, and `validation/`; no maintained direct file or additional direct-child role is permitted beneath `repo/`.

### FS-003-NR-005 — Closed `product/` Boundary

**Classification: M**

When `product/` is present, its maintained direct children shall be directories whose generic roles are limited to `design/`, `planning/`, `scripts/`, `specs/`, `src/`, and `validation/`; no maintained direct file or additional direct-child role is permitted beneath `product/`.

### FS-003-NR-006 — Selective Structural Closure

**Classification: S**

Closed hierarchy enforcement shall remain selective and shallow: it shall protect Design-declared architectural boundaries without requiring enumeration of ordinary nested implementation structure inside authorized extensible roles.

### FS-003-NR-007 — Architectural Namespace Ownership

**Classification: S**

Build shall not create a new architectural namespace at a closed boundary merely as an implementation convenience; a required new architectural role shall return upstream for the Design and Planning decisions that own it.

### FS-003-NR-010 — Operational Guidance Alignment

**Classification: B**

Active README and agent guidance shall describe `repo/` as reusable framework ownership, `product/` as generic product ownership, and closed architectural boundaries as constraints against incidental namespace invention without making operational guidance a second normative authority.

### FS-003-NR-011 — Structural Validation

**Classification: M**

Canonical Validation shall include a required `repository-structure` task that mechanically rejects maintained candidate paths outside the accepted closed root, `repo/`, and `product/` direct-child boundaries while permitting nested content inside authorized roles.

### FS-003-NR-012 — Product Work Readiness

**Classification: S**

Acceptance of FS-003 shall establish the generic structural ownership and placement needed to begin product Design and subsequent product lifecycle work under `product/` without requiring another framework Functional Set merely to establish that ownership or placement. This requirement does not assert that every framework-side lifecycle tool already discovers or processes product-owned lifecycle artifacts.

### FS-003-NR-013 — Canonical Product Lifecycle Substrate

**Classification: M**

When the maintained `product/` ownership domain is present, its baseline direct-child roles `design/`, `specs/`, `scripts/`, and `validation/` shall all be present as directories; `planning/` and `src/` remain authorized but optional until required by product lifecycle work.
