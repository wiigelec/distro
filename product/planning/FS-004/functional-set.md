---
functional_set: FS-004
title: Stage 1C Native Buildroot Completion
design_revision: 55506eb916345317a5d24853ffcbbba3a9fc5375
---

# FS-004 — Stage 1C Native Buildroot Completion

## Selected Design

The exact accepted Design state selected for reconciled Planning is `55506eb916345317a5d24853ffcbbba3a9fc5375`, integrating PR #13 after FS-003 Acceptance at `2d2f3773c208e7783efa3e2160f2fd524cf5d91a`. This includes the accepted DP-003/DP-005 Distro-maintained source and package-version amendments. Selected Product Design is `product/design/DP-001` through `DP-006`, especially DP-003 (shared manifests, dependency categories and recipe authority), DP-004 (Manage installed package operations), DP-005 (artifact, repository, installed-state and metapackage semantics) and DP-006 (complete native buildroot closure and verification).

## Functional Outcome

On a qualified foreign Linux host, Build consumes a verified Stage 1B handoff, produces the complete explicitly selected Stage 1C native package collection using the shared target-native execution mechanism, and delegates package creation and coherent collection publication to Manage. Manage resolves and installs the published `distro-buildroot` metapackage closure into a fresh target root, recording verifiable installed state. Build then uses that managed root via the normal production buildroot path to construct a representative native package with no undeclared Stage 1B or foreign-host userspace dependency.

## Included Scope

- The exact ten Stage 1B package names and versions, plus Linux headers 7.1.8 and Glibc 2.44 inherited as source selections from Stage 1A, rebuilt with Stage 1C-native recipes. The thirteen payload-bearing package identities, including the Distro-owned `filesystem` package, and the `distro-buildroot` metapackage must pass independent production-environment closure verification.
- Shared-manifest dependency semantics and selected relationship resolution; dependency-aware build order, per-package independent staging, and fixed package identities.
- Manage support for metadata-only metapackages, verified dependency closure, safe package installation into a designated fresh target root, installed-state authority, and a failure-safe candidate-to-authoritative collection boundary.
- Correct handling of required filesystem layout links and owned path collisions in the package model and managed root.
- One production Build native execution path whose root provider can be verified Stage 1B handoff during bootstrap or a Manage-installed package collection later.
- Independent closure verification and representative native execution in the fresh managed environment, plus failure and no-host-userspace negative evidence.
- Exact mechanical bindings and qualified-host evidence, Semantic Build Review and intentional Acceptance into `main` only after all gates pass.

## Excluded Scope

- Stage 2 `distro-base`, bootable OS installation and general system configuration.
- Final Distro-host generation-to-generation self-replication proof (expressly excluded by DP-006).
- Remote repository service, dynamic upstream version discovery, package scripting hooks, arbitrary upgrade/downgrade/removal policies, and general multi-operation rollback beyond the Stage 1C completion integrity requirements.
- A second Build engine, package writer, publisher, interpreter, or Stage 1C-specific managed-root assembler.

## Completion Boundary

FS-004 completes Stage 1C only when an independently verified, coherent `distro-buildroot` metapackage selection can be installed from Manage-published packages into a fresh root, and that root can run a representative production-mode native package build through the ordinary Build path without Stage 1B or undeclared host tools/libraries. Building the package list in the imported Stage 1B root alone does not meet this boundary. The selected collection must remain nonselectable as complete until its independent verification succeeds.

## Planning State

The DP-003/DP-005 Distro-maintained source amendments entered accepted `main` via PR #13 at `55506eb916345317a5d24853ffcbbba3a9fc5375`. This reconciliation pins FS-004 to that accepted Design state while retaining FS-003's historical acceptance revision. FS-004 Planning requires Semantic Planning Review against this revision before Build activation; reconciliation alone does not constitute Semantic Planning Review or FS-004 Acceptance. Mechanical requirements remain inactive until corresponding required validation tasks and bindings are constructed in Build. No FS-004 implementation or qualified-host closure evidence is claimed.
