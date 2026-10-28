---
doc_id: DP-002
title: Distro Bootstrap Architecture
depends_on:
  - DP-001
  - DP-003
  - DP-004
---

# Distro Bootstrap Architecture

## Purpose

Bootstrap is the one-time process that establishes Distro's native package-production capability and a minimal bootable Distro system capable of reproducing its foundational build environment.

The final self-replication proof runs the Stage 1 construction sequence on the booted Distro host, generates replacement `distro-buildroot` packages without publishing them, and compares their packaged file lists with those of the published Bootstrap packages. If the file lists are equivalent, the Distro-host-built packages replace the Bootstrap packages on the package server. File-list equivalence is the specified proof criterion; byte-for-byte artifact identity is not required.

Bootstrap is not a fourth permanent Distro component. Build produces package file contents and coordinates package production, Manage owns package creation, publication, and installed package state, and Install owns system installation and configuration, as established by DP-001.

## Bootstrap Implementation Location and Invocation

Bootstrap implementation source resides under `product/src/build/bootstrap/`. Bootstrap is invoked through Build's existing calling script, `product/scripts/build`, using Bootstrap-specific parameters. It does not have a separate top-level `product/scripts/bootstrap` entry point.

The Stage 1 command forms are specified below. Other Build CLI parameters and internal command syntax remain open. Locating Bootstrap within Build does not make it a fourth ongoing primary component.

## Shared Package Definitions and Selections

Bootstrap uses Build's user-maintained package manifests, context-specific package lists, and Bash recipes, as established by DP-003. Manifests define package identity, source information, verification, and dependencies; lists select explicit versions (including dependency versions) and stage-appropriate recipes; recipes provide package-specific construction commands. Bootstrap is a special configuration of the same host-agnostic Build engine, not a separate package-building engine. Build invocation parameters select host execution for Stages 1A and 1B, or construction inside `distro-buildroot` for Stage 1C and normal publishable builds. Stage 1C selects a local Bootstrap artifact instead of the package server as the source for establishing `distro-buildroot`. The host may be a foreign Linux distribution or Distro itself. Bootstrap does not maintain separate package definitions or hardcode package-specific construction behavior in Build's application code.

## Stage 1 — `distro-chroot`

Stage 1 is initially performed on a foreign Linux host and produces the initial published package collection needed to establish Distro's isolated production Build environment. Its three substages have explicit artifact handoffs.

### 1A — Cross-toolchain

```sh
./product/scripts/build cross-toolchain --root /path/to/rootdir
```

The `cross-toolchain` command selects host execution and the `cross-toolchain` package list. Build uses the shared manifests and selected list to identify package versions, acquire sources, and execute the selected Bash recipes. `--root` designates the Bootstrap workspace directory. The workspace contains `build/` for source extraction and compilation, `root/` for the installed `/` filesystem hierarchy, and `artifacts/` for archives of the installed filesystem. Build installs the cross-toolchain files into `root/` and archives the contents of `root/` into `artifacts/`. The archive, not the temporary build workspace, is the Stage 1A output consumed by Stage 1B. The archive format, filename, and detailed filesystem contents remain for subsequent Planning.

Linux From Scratch (LFS) Chapter 5, *Compiling a Cross-Toolchain*, is the principal technical reference. The prototype is reference material, not package or implementation authority.

**Output:** cross-toolchain artifact within `--root`, consumed by Stage 1B.

### 1B — Cross-chroot

```sh
./product/scripts/build cross-chroot \
  --root /path/to/rootdir \
  --cross-toolchain /path/to/crosstoolchainartifact
```

The `cross-chroot` command selects host execution and the distinct `cross-chroot` package list. `--cross-toolchain` supplies the Stage 1A artifact. Stage configuration determines how that artifact is extracted into the local `/` hierarchy under `--root` and made available to the selected recipes. Build handles source acquisition and recipe execution without hardcoding package-specific construction commands. The exact stage-configuration interface remains to be defined.

All construction is executed from the host, not by building inside the temporary chroot being created. Linux From Scratch (LFS) Chapter 6, *Cross Compiling Temporary Tools*, is the principal technical reference.

**Output:** cross-chroot artifact within `--root`, consumed by Stage 1C.

### 1C — Distro-buildroot Bootstrap Packages

```sh
./product/scripts/build distro-buildroot \
  --root /path/to/rootdir \
  --cross-chroot /path/to/crosschrootartifact
```

The `distro-buildroot` command selects its own package list and construction inside a `distro-buildroot` environment. Its package list is distinct from the `cross-chroot` list because recipe selections differ, even where package selections overlap. The `--cross-chroot` parameter supplies the Stage 1B artifact. Stage configuration determines how the local artifact supplies the buildroot environment; Build does not contain package-specific construction commands. The exact stage-configuration interface remains to be defined.

Normally the `distro-buildroot` environment is assembled from packages available on the package server. In this initial Bootstrap case, CLI parameters select the local cross-chroot artifact as the source because the initial packages do not yet exist on the server. This is the standard buildroot execution mode with an alternate input source, not a separate Build engine or execution mode.

The configured workflow has Build produce the staged files and invoke Manage to create and publish the initial **Bootstrap packages**, including the `distro-buildroot` metapackage and its required packages. Manage assembles each package from Build's files and publishes it using the standard creation and publication operations defined by DP-004. These are identified as Bootstrap packages independently of whether the host is a foreign Linux system or Distro itself.

`distro-buildroot` is a metapackage defining the requirements for the isolated production Build environment, not a preassembled chroot image. The environment constructed for Stage 1C remains distinct from the temporary cross-chroot artifact.

**Output:** published initial Bootstrap package collection, installable by Manage.

## Stage 2 — `distro-base`

Stage 2 begins on the foreign host. Manage installs the published `distro-buildroot` package collection to establish the isolated production Build environment. Build uses that environment to build and publish the `distro-base` packages required for a minimal bootable Distro system. All published packages built after the initial `distro-buildroot` bootstrap are built within an environment established from `distro-buildroot`.

Manage and Install use the published packages to construct the minimal system. Booting that system transfers execution to Distro's own kernel and userland.

### Self-Replication Proof and Package Replacement

On the booted Distro host, repeat the logical Stage 1 sequence using Distro as the host rather than the original foreign distribution. The repeated process must acquire and extract its own sources, build from source, and package the packages comprising the `distro-buildroot` collection, without relying on the foreign distribution's build tools or libraries.

The resulting Distro-host-built packages are **not** published immediately. Compare each generated package's packaged file list with that of its corresponding published Bootstrap package. If the lists are equivalent for the complete `distro-buildroot` collection, replace the published Bootstrap packages with the Distro-host-built equivalents. The replacement completes the Bootstrap self-replication proof. If the file lists are not equivalent, do not replace the published packages; Bootstrap's proof remains incomplete.

The comparison concerns the package file inventories, not byte-for-byte identity of archive contents. The exact comparison mechanism and publication transaction are left to further Design.

## Package Set and Capability Boundaries

`distro-buildroot` names the metapackage that defines Build's isolated environment. The corresponding package collection includes the dependency closure required to construct that environment and build source packages and their build dependencies as required by Build. The self-replication proof uses reconstruction of this foundational environment to demonstrate that Distro has bootstrapped its native package-production capability; it is not a claim that every possible package has been individually tested.

`distro-base` names the package set required for the minimal bootable Distro system. The exact inventories, dependency relationships, and overlap of these sets remain open.

The cross-toolchain artifact, cross-chroot artifact, production isolated Build environment, published package collections, and bootable Distro system are distinct outputs or environments. Bootstrap establishes the first production Build environment; Build owns subsequent package production through that environment.

## Progressive Decomposition

This document establishes the stage sequence, artifact handoffs, ownership boundaries, initial-package exception, and final proof. Package inventories, dependency resolution, chroot composition, artifact formats, source-selection policies, comparison mechanics, and publication procedures may be refined when needed for bounded Functional Sets. No Functional Set is implied to cover an entire Bootstrap stage.

The earlier `distro-proto` repository and LFS chapters are technical references, not independent authority over Distro Product Design.
