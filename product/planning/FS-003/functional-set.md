---
functional_set: FS-003
title: Stage 1C Initial Native Package Production
design_revision: 7092ff0b2cabba9b367ce06a42655bf2e7ba7692
---

# FS-003 — Stage 1C Initial Native Package Production

## Selected Design

The exact accepted Design revision consumed is `7092ff0b2cabba9b367ce06a42655bf2e7ba7692`.

Selected Product Design:

- `product/design/DP-001-product-architecture.md` — Build and Manage responsibilities and component boundaries.
- `product/design/DP-002-bootstrap-architecture.md` — Stage 1C invocation, Stage 1B input, and Bootstrap package outcome.
- `product/design/DP-003-build-package-definitions.md` — shared manifests, versioned selections, directly executed Bash recipes, and production execution mode.
- `product/design/DP-004-manage-architecture.md` — standard Manage create and publish operations.
- `product/design/DP-005-package-artifact-and-repository-architecture.md` — selected package identity, staging handoff, integrity, ownership, and publication semantics.
- `product/design/DP-006-buildroot-environment-architecture.md` — verified Stage 1B restoration, isolated native construction, and first Build-to-Manage package slice.

## Functional Outcome

On a qualified foreign Linux host, Build consumes a verified Stage 1B `cross-chroot` handoff, establishes an isolated target-native buildroot execution environment through the shared Build engine, and constructs a selected native package from an explicit-version package list using a directly executed Bash recipe.

Build stages the package's output independently of the temporary Bootstrap filesystem and supplies the selected package identity and manifest-derived relationships to Manage. Manage creates an independently verifiable Distro package artifact and publishes it into a local repository through its standard create and publish operations. The result is a first working Build-to-Manage package slice, not a complete production buildroot collection.

## Included Scope

- A bounded Stage 1C `distro-buildroot` invocation using a matching, verified Stage 1B archive and completion metadata.
- Initial target-native construction isolation with the same buildroot execution behavior intended for later production Build; Stage 1B is only the initial environment provider.
- A distinct Stage 1C package list with explicit versions, shared authoritative package manifests, and directly executed native Bash recipes for the selected package slice.
- Per-package staging separate from the imported temporary Bootstrap filesystem and from other package outputs.
- Build-to-Manage handoff of one fixed selected package identity, staged payload, and manifest-derived install-relevant relationships.
- Standard Manage package creation with target-root-relative payload, identity/integrity information, and installed-path ownership inventory.
- Standard Manage publication to a local repository with authoritative package records, verifiable artifacts, and failure-safe publication of the selected package.
- Independent verification of the package artifact and repository record without relying on the original construction workspace.
- Applicable mechanical validation and semantic review, with exact mechanical task bindings constructed during Build.

## Excluded Scope

- Building, publishing, or advertising the complete `distro-buildroot` dependency closure or metapackage as usable.
- General dependency-closure resolution, package installation, installed-state management, or assembly of a fresh production buildroot from Manage packages.
- Full Stage 1C closure verification, Stage 2 `distro-base`, bootable system installation, or native self-replication proof.
- General upgrades, removal, remote package transport, or full transaction rollback.
- A parallel Bootstrap engine, Build-owned package writer/publisher, alternate package format, or Stage 1C-only recipe interpreter.

## Completion Boundary

FS-003 is complete when a qualified host can validate and restore a Stage 1B handoff, construct at least one explicitly selected native package within the shared isolated buildroot execution mode, stage its files independently, and invoke the standard Manage operations to create and publish an independently verifiable package in a local repository. The resulting implementation must retain the accepted Build/Manage boundaries and be reusable by subsequent production package work.

This Functional Set does not claim a complete `distro-buildroot` environment or independent installation of its package closure. Its technical Plan, normative requirements, requirement states, and evaluation classifications remain to be produced and reviewed during Planning before implementation.
