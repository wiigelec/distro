---
functional_set: FS-001
title: Cross-Toolchain Construction
design_revision: ba3f0abd52df032d8229e3c500345abfeefaa08d
---

# FS-001 — Cross-Toolchain Construction

## Selected Design

The exact accepted Design revision is `ba3f0abd52df032d8229e3c500345abfeefaa08d`.

Selected Product Design:

- `product/design/DP-001-product-architecture.md` — Build ownership and component boundaries.
- `product/design/DP-002-bootstrap-architecture.md` — Bootstrap implementation and Stage 1A invocation, host execution, workspace layout, output and Stage 1B artifact handoff.
- `product/design/DP-003-build-package-definitions.md` — shared manifests, explicitly versioned lists, Bash recipes, source acquisition and execution responsibilities.
- `product/design/DP-004-manage-architecture.md` — boundary excluding Manage package creation/publication from Stage 1A's filesystem archive.

## Functional Outcome

From a foreign Linux host, invoking `./product/scripts/build cross-toolchain --root /path/to/rootdir` constructs a usable initial cross-toolchain using the common Build engine and user-maintained package definitions. Build installs the resulting toolchain filesystem under `rootdir/root/` and archives that filesystem under `rootdir/artifacts/` for Stage 1B. `rootdir/build/` holds source extraction and construction work and is excluded from the archived filesystem.

## Included Scope

- Bootstrap Stage 1A command and its integration with the shared Build engine.
- Stage 1A-specific package list with explicit versions and selected Bash recipes, authoritative package manifests, source retrieval and verification.
- Source extraction, build workspace preparation, direct recipe execution, staged installation into the selected filesystem root, and cross-toolchain artifact creation.
- A coherent initial cross-toolchain capable of supporting the stated Stage 1B handoff.
- Necessary package-order/dependency handling, host/toolchain execution context, failure behavior and tests for the bounded Stage 1A construction.
- Applicable product mechanical validation tasks and their bindings, constructed by Build from the approved normative requirements.

## Excluded Scope

- Execution of Stage 1B (`cross-chroot`), Stage 1C (`distro-buildroot`) or Stage 2 (`distro-base`).
- Manage-created Distro packages, publication, repository transactions or installed-package database state.
- A generic buildroot/chroot executor, dynamic upstream release discovery, Git source checkout support, or a general package management engine.
- Bootable system construction and final Bootstrap self-replication proof.

## Completion Boundary

FS-001 is complete when the Stage 1A entry point can construct the selected toolchain from the specified sources on an appropriately qualified foreign Linux host, produce the independently consumable filesystem archive, and pass the applicable mechanical and semantic review gates. Functional Set completion does not assert that Stage 1B has been implemented or executed.
