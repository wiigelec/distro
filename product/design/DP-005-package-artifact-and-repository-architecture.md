---
doc_id: DP-005
title: Package Artifact and Repository Architecture
depends_on:
  - DP-001
  - DP-003
  - DP-004
---

# Package Artifact and Repository Architecture

## Purpose and ownership

Distro packages are the durable, independently consumable results of Build-produced files. Manage creates package artifacts and metadata, publishes them to a repository, and applies them to target roots. Build owns source selection, construction, staging, and the authoritative manifest-derived dependency inputs; it does not construct package archives, publish package records, or maintain installed state.

The same package representation and Manage operations serve the initial Stage 1C Bootstrap packages and subsequent production packages. Bootstrap is not a second package system.

## Package identity

A published package is identified by **name, upstream version, target architecture, and Distro packaging revision**. The revision distinguishes packaging changes for the same upstream version and architecture; artifact checksums identify particular bytes and are not package identity. A published identity must not silently change its install-relevant package relationships or owned-path inventory. The exact revision allocation and identity grammar are deferred until their bounded specification is needed.

## Build-to-Manage interface

Build provides Manage with a per-package staged filesystem, the selected package identity, and the manifest-derived package relationships relevant to installation. Manage consumes this input without reading build recipes or inventing dependency relationships. Each package's staged payload remains distinct from both the temporary Bootstrap filesystem and other packages' staged payloads.

Manage creates a package artifact containing an installable target-root-relative payload and enough embedded identity to verify that it is the selected artifact. The repository's authoritative package record associates the identity with package relationships, its installed-path inventory, artifact location, and integrity checksum. The package archive need not duplicate the repository's full dependency graph. A package may have no payload, as with a metapackage.

The archive serialization, compression choice, exact metadata fields and handoff directory conventions are technical decisions for bounded Planning, provided the identity, integrity, ownership and independent-consumption contracts are preserved.

## Dependency and filesystem semantics

The authoritative Build manifests established in DP-003 remain the single source of package dependency declarations and dependency categories. Build supplies the selected, resolved relationships to Manage; Manage represents the resulting install-relevant relationships in the repository and installed state. A package list, recipe, generated ELF audit, or metapackage generator does not independently define ordinary package dependencies. A runtime audit may detect omissions but cannot silently replace the manifests' semantic authority.

Manage must identify which installed non-directory paths belong to each package and must detect conflicts before applying conflicting payloads. Ordinary shared directories may exist without treating every directory as an exclusive package claim. Legitimate target-root symlinks, including the accepted merged-`/usr` layout, must remain representable and safe to apply. Filesystem layout links and other installed content must derive from explicit package ownership or a separately established filesystem policy; Manage must not silently repair them as unowned installation side effects.

Package creation and application reject unsafe paths, inappropriate archive member types, and escapes from the selected target root. A target-root-relative path is not permission to modify the host filesystem. Detailed archive parsing, symlink resolution, and hardlink handling remain implementation/Planning subjects subject to this boundary.

## Repository and publication

The initial repository may be a local directory containing package artifacts and an authoritative index; no package server or remote transport is required merely to bootstrap. The index is the publication authority for selectable package identities and their corresponding verified artifacts. Publication must not expose a package index entry before its referenced artifact is complete and integrity-verifiable. A failed publication must not leave an authoritative index that points to absent, incomplete, or unverified artifacts. Replacing an existing published selection must not invalidate the previously usable selection before the replacement is ready.

Manage owns both `create` and `publish` as distinct operations under DP-004. Build may orchestrate those operations but does not implement an alternative publisher. Exact repository files, index serialization, concurrency policy and atomic-update mechanisms are left to Planning when required.

## Installation and installed state

Manage resolves package relationships from the authoritative repository, verifies selected artifacts, checks planned ownership conflicts, and applies package payloads to a designated target root. The target root maintains Manage-owned installed state containing sufficient identity, ownership, artifact integrity and dependency information for later package operations without requiring Build's construction records. Installation failure must not present incomplete application as a successfully installed package collection.

A package database and a target's installed-state database have distinct authority. Published metadata describes available packages; installed state describes what was actually applied to that root.

## Bootstrap metapackages

A metapackage is an ordinary package identity with no required payload and dependency relationships that select a coherent package collection. `distro-buildroot` is such a metapackage. Its dependency meaning originates in its authoritative manifest, and its concrete selected closure is resolved through the same package model as other packages. It is not a chroot archive or a separate construction engine.

## Design limits

This design establishes the minimal durable package semantics required for Stage 1C. It does not decide dynamic version discovery, public mirrors, signatures for untrusted distribution, arbitrary upgrade/downgrade policies, package scripting hooks, or full transaction rollback. Those concerns may be elaborated when a bounded Functional Set needs them. The `distro-proto` G1 package and Manage paths are migration references, not normative authority.
