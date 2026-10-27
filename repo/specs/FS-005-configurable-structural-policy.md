# FS-005 — Configurable Structural Policy Normative Requirements

### FS-005-NR-001 — Closed Boundary Preservation

**Classification: B**

The maintained repository-root boundary and direct-child boundaries of `repo/` and `product/` shall remain closed and default-deny; externalizing concrete authorization into configuration shall not make an undeclared maintained entry permissible.

### FS-005-NR-002 — Canonical Structural Policy

**Classification: M**

The repository shall contain canonical `repo/validation/structure-policy.json`, and framework structural Validation shall obtain concrete authorized-entry data from that file rather than from a second hardcoded allowlist.

### FS-005-NR-003 — Strict Policy Schema

**Classification: M**

The canonical structural policy shall conform exactly to the FS-005 version-1 schema and fail closed for a missing file, malformed JSON, unknown keys, invalid direct-child names, duplicate entries, root file/directory overlap, or required product roles outside the authorized product-directory set.

### FS-005-NR-004 — Default Policy Compatibility

**Classification: B**

The canonical default structural policy shall authorize exactly the roles authorized by the pre-FS-005 hardcoded policy, including existing required baseline product roles, so externalization alone neither broadens nor narrows accepted default structure.

### FS-005-NR-005 — Policy-Driven Root Enforcement

**Classification: M**

`repository-structure` shall allow maintained repository-root direct files and directories only when explicitly authorized by the validated policy and shall reject undeclared root entries.

### FS-005-NR-006 — Policy-Driven Ownership-Tree Enforcement

**Classification: M**

`repository-structure` shall allow maintained direct children of `repo/` and `product/` only when explicitly authorized by the validated policy, shall require those direct children to be directories, and shall preserve nested extensibility below authorized roles unless another requirement constrains it.

### FS-005-NR-007 — Required Product Roles

**Classification: M**

When maintained `product/` exists, `repository-structure` shall require every role listed by `product.required_when_present`, and the policy validator shall require those roles to be a subset of authorized product directories.

### FS-005-NR-008 — Configuration Is Not Normative Authority

**Classification: S**

The structural-policy file shall remain a mechanical representation of accepted structural authorization and shall not independently create Design meaning, normative requirements, ownership semantics, or permission for an unjustified architectural change.

### FS-005-NR-009 — Framework and Policy Separation

**Classification: S**

Reusable framework Validation code shall own policy-schema interpretation and enforcement mechanics, while an installed repository may intentionally carry concrete policy values different from supplier defaults without those values becoming a fork of framework implementation.

### FS-005-NR-010 — Derived Repository Adaptation

**Classification: B**

An installed repository shall be mechanically capable of carrying an intentional repository-local policy change that authorizes additional schema-valid direct entries while leaving undeclared entries denied and without modifying reusable framework Validation code.

### FS-005-NR-011 — Framework Source Truthfulness

**Classification: B**

Repository-local structural-policy values may differ from supplier defaults after intentional repository development without changing the truthful meaning of framework source identity as the supplying reusable framework revision.

### FS-005-NR-012 — No Generalized Policy Engine

**Classification: S**

FS-005 shall not introduce wildcard, glob, regex, recursive authorization, ordered override, plugin, or generalized policy-engine semantics; version 1 is a finite explicit direct-child allowlist representation.
