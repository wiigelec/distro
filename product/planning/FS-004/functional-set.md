---
functional_set: FS-004
title: Stage 1C Native Buildroot Completion
design_revision: 2d2f3773c208e7783efa3e2160f2fd524cf5d91a
---

# FS-004 — Stage 1C Native Buildroot Completion

## Selected Design

The exact accepted repository state consumed by Planning is `2d2f3773c208e7783efa3e2160f2fd524cf5d91a`, following FS-003 Acceptance. Selected Product Design is `product/design/DP-001` through `DP-006`, especially DP-003 (shared manifests, dependency categories and recipe authority), DP-004 (Manage installed package operations), DP-005 (artifact, repository, installed-state and metapackage semantics) and DP-006 (complete native buildroot closure and verification).

## Functional Outcome

On a qualified foreign Linux host, Build consumes a verified Stage 1B handoff, produces the complete explicitly selected Stage 1C native package collection using the shared target-native execution mechanism, and delegates package creation and coherent collection publication to Manage. Manage resolves and installs the published `distro-buildroot` metapackage closure into a fresh target root, recording verifiable installed state. Build then uses that managed root via the normal production buildroot path to construct a representative native package with no undeclared Stage 1B or foreign-host userspace dependency.

## Included Scope

- A complete, explicit-version Stage 1C package selection and reproducible native recipes, including compiler/toolchain, native runtime, tools, headers and other dependencies required by the selected workload.
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

This file selects the Functional Set and Design. The accompanying Plan and normative specification are proposed Planning outputs. Mechanical requirements remain inactive until corresponding required validation tasks and bindings are constructed in Build. No code completion, qualified-host evidence, Semantic Review or Acceptance is claimed by these documents.
