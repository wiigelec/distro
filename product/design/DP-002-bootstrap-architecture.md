---
doc_id: DP-002
title: Distro Bootstrap Architecture
depends_on:
  - DP-001
  - DP-003
---

# Distro Bootstrap Architecture

## Purpose

Bootstrap is the one-time process that establishes Distro's native package-production capability and a minimal bootable Distro system capable of reproducing its foundational build environment.

The final self-replication proof runs the Stage 1 construction sequence on the booted Distro host, generates replacement `distro-buildroot` packages without publishing them, and compares their packaged file lists with those of the published foreign-host-built packages. If the file lists are equivalent, the Distro-host-built packages replace the foreign-host-built packages on the package server. File-list equivalence is the specified proof criterion; byte-for-byte artifact identity is not required.

Bootstrap is not a fourth permanent Distro component. Build owns ongoing package production, Manage owns installed package state, and Install owns system installation and configuration, as established by DP-001.

## Bootstrap Implementation Location and Invocation

Bootstrap implementation source resides under `product/src/build/bootstrap/`. Bootstrap is invoked through Build's existing calling script, `product/scripts/build`, using Bootstrap-specific parameters. It does not have a separate top-level `product/scripts/bootstrap` entry point.

The exact parameters and command syntax remain open. Locating the Bootstrap implementation within Build does not make Bootstrap a fourth ongoing primary component.

## Shared Package Definitions and Selections

Bootstrap uses Build's user-maintained package manifests and context-specific package lists, as established by DP-003. Package manifests define package identity, source information, and dependencies; package lists select versions and build configurations for each Bootstrap stage. Bootstrap does not maintain a separate set of package definitions or hardcode package-specific construction behavior.

## Stage 1 — `distro-chroot`

Stage 1 is initially performed on a foreign Linux host and produces the initial published package collection needed to establish Distro's isolated production Build environment. Its three substages have explicit artifact handoffs.

### 1A — Host (Cross) Build

On the foreign host, construct the cross-toolchain artifact required by Stage 1B. Linux From Scratch (LFS) Chapter 5, *Compiling a Cross-Toolchain*, is the principal technical reference.

**Output:** cross-toolchain artifact.

### 1B — Temporary Chroot Construction

On the foreign host, use the Stage 1A cross-toolchain to construct the temporary Distro chroot. All Stage 1B construction takes place from the foreign host; Stage 1B does not execute native builds inside the chroot it is constructing. The temporary chroot becomes functional only upon completion of Stage 1B. LFS Chapter 6, *Cross Compiling Temporary Tools*, is the principal technical reference.

**Output:** temp-chroot artifact, available for use by Stage 1C.

### 1C — Bootstrap Build Environment and Publish Packages

Use the Stage 1B temp-chroot artifact to bootstrap the initial production package collection, including the `distro-buildroot` metapackage and its required packages. Publish the initial collection to the package server so Manage can install it and establish a production Build environment. This initial bootstrapping is the exception required before `distro-buildroot` can itself be used to build published packages.

`distro-buildroot` is a metapackage defining the package requirements for Build's isolated build environment. It is not itself a preassembled chroot image. Manage installs its required package set to create that environment; the resulting environment is not a copy of the temporary Stage 1B chroot.

**Output:** published initial `distro-buildroot` package collection, installable by Manage.

## Stage 2 — `distro-base`

Stage 2 begins on the foreign host. Manage installs the published `distro-buildroot` package collection to establish the isolated production Build environment. Build uses that environment to build and publish the `distro-base` packages required for a minimal bootable Distro system. All published packages built after the initial `distro-buildroot` bootstrap are built within an environment established from `distro-buildroot`.

Manage and Install use the published packages to construct the minimal system. Booting that system transfers execution to Distro's own kernel and userland.

### Self-Replication Proof and Package Replacement

On the booted Distro host, repeat the logical Stage 1 sequence using Distro as the host rather than the original foreign distribution. The repeated process must acquire and extract its own sources, build from source, and package the packages comprising the `distro-buildroot` collection, without relying on the foreign distribution's build tools or libraries.

The resulting Distro-host-built packages are **not** published immediately. Compare each generated package's packaged file list with that of its corresponding published foreign-host-built package. If the lists are equivalent for the complete `distro-buildroot` collection, replace the published foreign-host-built packages with the Distro-host-built equivalents. The replacement completes the Bootstrap self-replication proof. If the file lists are not equivalent, do not replace the published packages; Bootstrap's proof remains incomplete.

The comparison concerns the package file inventories, not byte-for-byte identity of archive contents. The exact comparison mechanism and publication transaction are left to further Design.

## Package Set and Capability Boundaries

`distro-buildroot` names the metapackage that defines Build's isolated environment. The corresponding package collection includes the dependency closure required to construct that environment and build source packages and their build dependencies as required by Build. The self-replication proof uses reconstruction of this foundational environment to demonstrate that Distro has bootstrapped its native package-production capability; it is not a claim that every possible package has been individually tested.

`distro-base` names the package set required for the minimal bootable Distro system. The exact inventories, dependency relationships, and overlap of these sets remain open.

The cross-toolchain artifact, temp-chroot artifact, production isolated Build environment, published package collections, and bootable Distro system are distinct outputs or environments. Bootstrap establishes the first production Build environment; Build owns subsequent package production through that environment.

## Progressive Decomposition

This document establishes the stage sequence, artifact handoffs, ownership boundaries, initial-package exception, and final proof. Package inventories, dependency resolution, chroot composition, artifact formats, source-selection policies, comparison mechanics, and publication procedures may be refined when needed for bounded Functional Sets. No Functional Set is implied to cover an entire Bootstrap stage.

The earlier `distro-proto` repository and LFS chapters are technical references, not independent authority over Distro Product Design.
