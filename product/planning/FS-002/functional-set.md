---
functional_set: FS-002
title: Cross-Chroot Temporary Tools
design_revision: 502a1280ccd6fbb845179435c0cd2069d86adc0a
---

# FS-002 — Cross-Chroot Temporary Tools

## Selected Design

The accepted Design state consumed is repository revision `502a1280ccd6fbb845179435c0cd2069d86adc0a`.

- `product/design/DP-001-product-architecture.md` — Build ownership and boundaries with Manage and Install.
- `product/design/DP-002-bootstrap-architecture.md` — Stage 1B invocation, host-executed construction, Stage 1A import and Stage 1C handoff.
- `product/design/DP-003-build-package-definitions.md` — shared package manifests, exact-version lists, and directly executed Bash recipes.
- `product/design/DP-004-manage-architecture.md` — package management and publication boundaries.

## Functional Outcome

`./product/scripts/build cross-chroot --root <rootdir> --cross-toolchain <artifact>` consumes a validated Stage 1A archive, builds the selected temporary target-native tools by executing cross-compilation recipes on the host through the existing Build engine, and publishes a verified cross-chroot filesystem handoff for Stage 1C. The archive is usable independently of the Stage 1B build workspace.

## Included Scope

- A Stage 1B entry point and narrowly scoped orchestration using the existing Build, source-verification, and sandbox facilities.
- Validation and safe restoration of the Stage 1A archive and its `cross-toolchain.json` completion metadata.
- New shared YAML manifests for missing prototype package identities; reuse of existing Binutils and GCC manifests; ordered cross-chroot YAML package list with versions, digests, and recipe selections.
- Direct Bash recipes adapted from the `proto/distro-bootstrap-chroot` temporary-tools prototype, preserving necessary compiler and runtime integration behavior without adopting its JSON recipe interpreter.
- Controlled installation into the target filesystem, including imported-file collision handling, and source/build/install/artifact separation.
- Functional verification of target-native tools and a portable, integrity-checked Stage 1B archive/metadata handoff.
- Product mechanical evaluation tasks and exact bindings for applicable active normative requirements.

## Excluded Scope

- Stage 1C construction within `distro-buildroot`, Manage package assembly/publication and installed-package state, or Stage 2 system installation.
- Native generation-A-to-B rebuild or final self-replication proof; the prototype's experimental native rebuild driver is not carried into this Functional Set.
- An independent Bootstrap engine, JSON build-command interpreter, generic package manager, or expansion to a full LFS Chapter 6 inventory merely because those packages appear in the reference.

## Completion Boundary

FS-002 is complete when a qualified host can consume a valid Stage 1A handoff, construct the selected functional temporary-tools target root with direct Bash recipes, demonstrate the target-native capabilities needed for its bounded Stage 1C handoff, and publish an independently verified archive plus metadata. Required mechanical validation and semantic review must be satisfactory before intentional integration into `main` constitutes Acceptance.

## Initial Requirement State

During Planning, FS-002-NR-001 through FS-002-NR-012 and FS-002-NR-014 are inactive until Build implements their enforcement and Planning reactivates them. FS-002-NR-013 and FS-002-NR-015 remain active for semantic evaluation. Evaluation classifications are unchanged; inactive requirements do not impose current mechanical or semantic evaluation obligations. Reactivation and required bindings precede acceptance.

## Implementation Evaluation State

The initial inactive requirement state above records the Planning baseline. Following Build implementation, FS-002-NR-001 through FS-002-NR-012 and FS-002-NR-014 were activated in the normative specification and assigned required product mechanical-validation tasks. This transition does not itself establish Semantic Review or Acceptance. Successful native-tool and relocation execution must be corroborated with qualified-host handoff evidence.
