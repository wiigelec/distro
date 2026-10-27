---
doc_id: DP-002
title: Distro Bootstrap Architecture
depends_on:
  - DP-001
---

# Distro Bootstrap Architecture

## Purpose

Bootstrap is the one-time process that creates the minimal Distro package set needed to construct a bootable Distro system capable of replicating itself.

Self-replication means that the booted Distro system can download, extract, build from source, and package all packages that comprise the bootstrap package set. The final proof is to repeat Stage 1 on the booted Distro host without dependence on the original foreign distribution's build tools and libraries. This describes functional replication; it does not yet require byte-for-byte identical artifacts.

Bootstrap is not a fourth permanent Distro component. Once Bootstrap has established the initial package collections and demonstrated self-replication, ongoing package production belongs to Build, installed package state belongs to Manage, and system installation belongs to Install.

## Stage 1 — `distro-chroot`

Stage 1 initially runs under a foreign Linux host kernel and creates the production package set named `distro-buildroot`. Its three substages have distinct artifact handoffs.

### 1A — Host (Cross) Build

Using the foreign host, construct a cross-toolchain artifact for Stage 1B. The principal technical reference is Linux From Scratch (LFS) Chapter 5, *Compiling a Cross-Toolchain*. The exact toolchain contents and construction procedures remain open for further Design.

**Output:** cross-toolchain artifact.

### 1B — Native Chroot Build

Use the cross-toolchain artifact to construct a temporary Distro chroot artifact for Stage 1C. LFS Chapter 6, *Cross Compiling Temporary Tools*, is the principal reference for construction of this temporary environment.

In the native chroot, Distro tools perform the `configure`, `make`, and `make install` work. At this stage the foreign host supplies the kernel and remains responsible for source download, extraction, and packaging of build output. The temporary chroot is a construction environment, not the definitive production Build chroot.

**Output:** temp-chroot artifact.

### 1C — Production Package Build and Publication

Use the temp-chroot artifact to build and package the closed production Distro package set `distro-buildroot`, then publish it to the package server.

`distro-buildroot` contains the packages needed to establish the native production Build chroot, including the package closure needed to build its own constituent software from source. Manage must be able to consume the published packages to create that Build chroot. The Build chroot is assembled from the production packages, not copied wholesale from the temporary chroot.

**Output:** published `distro-buildroot` package set.

## Stage 2 — `distro-base`

Stage 2 begins on the foreign host using the published `distro-buildroot` packages. Manage creates the production Build chroot from those packages. The Build environment builds and publishes the `distro-base` package set required for a minimal bootable Distro system.

Manage and Install then use the published packages to construct that system. Booting it transfers execution from the foreign host kernel to Distro's own kernel.

The final Stage 2 proof is to repeat Stage 1 on the booted Distro host. In this repetition, Distro performs its own source download, extraction, building, and packaging instead of relying on the original foreign distribution. Successfully reproducing the bootstrap package set establishes the intended self-replication capability.

## Package Sets and Environment Boundaries

`distro-buildroot` is the closed production package set for the native Build chroot. `distro-base` is the package set for the minimal bootable Distro system. Their exact package inventories, dependency relationships, and any overlap remain for later Design.

The cross-toolchain, temporary chroot, production Build chroot, and bootable Distro system are distinct artifacts or environments with different roles. Stage 1 produces published packages; the definitive Build chroot is installed from those packages through Manage.

## Progressive Decomposition

This document establishes the intended stages, responsibilities, outputs, and final proof. Later Design may elaborate stage construction, package membership and closure, artifact formats, source selection, package publication, installation details, and validation criteria as the selected Functional Set requires. No single Functional Set is implied to cover an entire Bootstrap stage.

The prior `distro-proto` work and LFS chapters are technical references, not independent authority over Distro Product Design.
