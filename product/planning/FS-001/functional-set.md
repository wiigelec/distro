---
functional_set: FS-001
title: Cross-Toolchain Construction
design_revision: 436e44f25179504f9d3a28f3b1fbef96f9c746f0
---

# FS-001 — Cross-Toolchain Construction

## Selected Design

The exact accepted Design revision is `436e44f25179504f9d3a28f3b1fbef96f9c746f0`.

Selected Product Design:

- `product/design/DP-001-product-architecture.md` — Build ownership and component boundaries.
- `product/design/DP-002-bootstrap-architecture.md` — Bootstrap implementation and Stage 1A invocation, host execution, workspace layout, output and Stage 1B artifact handoff.
- `product/design/DP-003-build-package-definitions.md` — shared manifests, explicitly versioned lists, Bash recipes, source acquisition and execution responsibilities.
- `product/design/DP-004-manage-architecture.md` — boundary excluding Manage package creation/publication from Stage 1A's filesystem archive.

## Functional Outcome

From a foreign Linux host, invoking `./product/scripts/build cross-toolchain --root /path/to/rootdir` constructs a usable initial cross-toolchain using the common Build engine and user-maintained package definitions. Build installs the resulting toolchain filesystem under `rootdir/root/` and archives that filesystem under `rootdir/artifacts/` for Stage 1B. `rootdir/build/` holds source extraction and construction work and is excluded from the archived filesystem.

## Included Scope

- Bootstrap Stage 1A command and its integration with the shared Build engine.
- Stage 1A-specific package list with explicit versions and selected Bash recipes, authoritative package manifests, source retrieval and verification, and verified supporting GCC inputs.
- Source extraction, build workspace preparation, direct Bash recipe execution within controlled host sandbox isolation, staged installation into the selected filesystem root, and cross-toolchain artifact creation.
- A coherent initial cross-toolchain demonstrably usable after archive restoration into a different absolute host workspace through the same sandbox-visible target layout.
- Necessary package-order/dependency handling, sandboxed host/toolchain execution context, protection against accidental host writes and environment leakage, fail-closed isolation, failure behavior and tests for the bounded Stage 1A construction.
- Applicable product mechanical validation tasks and their bindings, constructed by Build from the approved normative requirements.

## Excluded Scope

- Execution of Stage 1B (`cross-chroot`), Stage 1C (`distro-buildroot`) or Stage 2 (`distro-base`).
- Manage-created Distro packages, publication, repository transactions or installed-package database state.
- A generic buildroot/chroot executor, dynamic upstream release discovery, Git source checkout support, or a general package management engine.
- Bootable system construction and final Bootstrap self-replication proof.

## Completion Boundary

FS-001 is complete when the Stage 1A entry point can construct the selected toolchain from the specified sources on an appropriately qualified foreign Linux host, produce the independently consumable filesystem archive, and pass the applicable mechanical and semantic review gates. Functional Set completion does not assert that Stage 1B has been implemented or executed.
