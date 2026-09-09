---
doc_id: DP-013
title: Repository Ownership and Structural Boundaries
depends_on:
  - DP-001
  - DP-010
  - DP-012
---

# Repository Ownership and Structural Boundaries

## Purpose

The repository framework is portable across products. It separates reusable repository-development framework state from the product-owned state developed through that framework while keeping the repository structure understandable and mechanically protectable.

## Ownership Domains

`repo/` is the reusable repository/framework ownership domain.

It contains the Design, Planning, normative specifications, implementation, entry points, and Validation that define or realize the portable repository-development framework itself.

`product/` is the generic product ownership domain.

It contains the Design, Planning, normative specifications, implementation, entry points, and Validation owned by whatever product a particular repository develops. The framework defines the role and structural boundary of `product/`; it does not define or pin the product's identity, semantics, technology, architecture, or feature set.

Repository/framework work and product work use the same lifecycle responsibilities. Their artifacts remain in the ownership domain whose meaning and behavior they govern.

## Other Repository State

Repository-root operational surfaces such as `README.md`, `AGENTS.md`, hosting integration, licensing, and explicitly user-owned material may exist outside the two ownership trees when their repository role requires it.

`user/` remains user-owned operational material outside framework and product normative ownership.

For structural ownership, maintained repository state is content intended to participate in persistent candidate or accepted repository state. Transient ignored local state is outside structural closure merely by existing; content intended to become accepted state must use an authorized structural role rather than rely on ignore rules to evade that boundary.

## Closed Structural Boundaries

Design may declare an architectural boundary closed.

The maintained repository-root boundary and the direct-child boundaries of `repo/` and `product/` are closed architectural boundaries. Planning establishes the concrete authorized roles within those Design-declared boundaries.

At a closed boundary, an entry is permitted only when the governing structure explicitly authorizes its role. Absence of an explicit prohibition is not permission to create a new architectural namespace.

Closed boundaries should be shallow and selective. They protect architectural ownership and major repository roles; they do not require every nested implementation directory or source package to be enumerated.

A namespace may be explicitly extensible. Ordinary Build decisions may create content inside an extensible namespace when that content preserves the namespace role and governing upstream intent.

## Architectural Change Boundary

Build may choose ordinary files, modules, packages, and nested organization inside an extensible implementation namespace.

Build shall not create a new direct child at a closed architectural boundary merely for implementation convenience. If an existing boundary cannot express required behavior cleanly, work returns upstream so Design can decide whether the repository architecture changes and Planning can derive the corresponding obligations.

## Product Portability

The generic `product/` contract must remain usable for products unrelated to the repo-spec initializer.

Framework behavior may supply generic product-development surfaces and structural constraints, but product-specific meaning belongs to product Design and Planning rather than repository/framework Design.

## Canonical Product Validation Substrate

The generic product ownership domain includes a canonical Validation substrate so that a repository can begin product lifecycle work without inventing a second validation architecture.

`product/design/` is the product-owned Design surface and `product/specs/` is the product-owned normative-specification surface.

`product/scripts/validate` is the canonical product Validation entry point. It is an operational entry point for the product domain rather than an ownership location for substantive validation predicates or implementation.

`product/validation/` owns the product Requirement Evaluation Manifest and the product-owned mechanical validation implementation, tasks, and fixtures required to evaluate product normative requirements.

The product Requirement Evaluation Manifest records exact bindings from mechanically evaluated product normative requirements to product validation tasks. An empty manifest is valid when no applicable product normative requirement currently requires mechanical evaluation; emptiness does not remove the product Validation substrate or its ownership boundaries.

Framework Validation shall mechanically enforce the reliably decidable structural validity and requirement-to-task traceability contract of this generic product Validation substrate. Such framework enforcement protects the lifecycle architecture and requirement-to-task traceability; it does not define product-specific normative predicates, evaluate product semantic meaning, execute product-owned validation predicates, or transfer product Validation ownership into `repo/`.

## Validation

Closed structural boundaries are mechanically decidable where their permitted direct entries are explicit.

Validation may enforce those boundaries directly. Such enforcement protects accepted structure but does not independently create a new namespace, ownership rule, or product semantic.

## Repository-Wide Operational Composition

Repository-root `scripts/` is an authorized operational composition role.

It may contain repository-wide entry points that coordinate already-owned framework and product operations when a repository-level command is necessary. This role does not own framework meaning, product meaning, normative requirements, or domain implementation. It delegates to authoritative entry points of the ownership domains it coordinates.

The root operational composition role remains narrow. It shall not become a parallel framework implementation tree, product implementation tree, generalized plugin namespace, or substitute for domain ownership.

## Portable History Boundary

The reusable framework must remain operational when installed into a repository whose Git history is independent from the framework-supplying repository.

Framework artifacts may retain exact identifiers from their originating history where those identifiers preserve meaning or traceability. Retaining such an identifier does not require the originating commit object, ancestry, remote, graft, replace ref, or other supplier-history machinery to remain present in the current repository unless Design explicitly requires that dependency.

Ordinary lifecycle use therefore distinguishes preserved historical identifiers from current-repository ancestry.

An installed framework snapshot may omit framework-development history that is not required for the installed framework's operation. In particular, framework Planning artifacts need not be carried into a derived repository when an installed-framework source record identifies the supplied framework state and the remaining installed artifacts preserve the framework meaning and enforceable normative state.
