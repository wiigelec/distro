---
doc_id: DP-003
title: Build Package Definitions and Selections
depends_on:
  - DP-001
---

# Build Package Definitions and Selections

## Purpose

Build and Bootstrap use a shared, configuration-driven package model. Adding a package within the capabilities supported by Build requires creating or updating package manifests and appropriate package lists, not changing application source code. Package-specific configuration belongs exclusively to manifests and lists; Build supplies generic mechanisms to interpret and execute that configuration.

## Package Manifests — Static Definitions

Package manifests form one authoritative, user-maintained collection under `product/src/build/packages/`. The collection consists of multiple files, which users may organize in subdirectories by functionality or any other scheme. File organization does not determine package identity or behavior. A manifest is static in the sense that it describes the package independently of any particular build request; it remains user-editable.

Manifests define package identity and characteristics, including package name, upstream project URL, release URL, version formatting or interpretation, package-specific build requirements and instructions, and dependencies. The manifest collection is the **sole source of package dependency declarations**. Package lists cannot add, replace, or override those declarations.

Dependencies have three categories:

- **Build tools:** needed to construct the package, but not required on the installed target solely because they were build tools.
- **Build link dependencies:** needed to construct the package and declared as requirements of the installed package.
- **Runtime dependencies:** needed by the installed package, regardless of whether they are needed during its construction.

Where dependency requirements vary with build context, that conditional meaning must be expressed by the package definition rather than redefined by a package list. The schema and condition mechanism remain open.

## Package Lists — Dynamic Build Selections

Package lists specify which packages a Build or Bootstrap operation requests and how to build them. They reference manifests rather than duplicating package definitions or dependencies. A list selects a version strategy for each requested package and carries build-context configuration such as compiler flags, configure options, toolchain/target selection, and other applicable build parameters.

Initially, version selections are fixed, explicit versions. Future Design may allow strategies including `stable`, `latest`, a version series such as `5.3`, and Bootstrap selections derived from the host environment. Version interpretation and release discovery use information supplied by manifests; version *selection* belongs to lists.

The same manifest can be used with different lists and build configurations. For example, GCC may be built as an initial cross-compiler, for a temporary bootstrap environment, and as a final native Distro compiler without creating separate GCC definitions or hardcoded GCC paths in Build's source.

Package-list storage location, file format, configuration precedence, version-strategy resolution, and list maintenance policy remain open.

## Execution and Component Boundaries

Build operates as a generic engine driven by manifests and lists. Bootstrap, implemented within Build, uses the same package definitions and selection model for its stages. Build may provide generic support for build systems and operations, but must not require package-specific source-code changes to add a package expressible through those capabilities.

Build resolves build requirements from manifests and produces package metadata for Manage. Manage consumes published package dependency information for installation; it does not maintain another authoritative source of dependency declarations. Install uses Manage for package installation.

The `distro-buildroot` metapackage defines the requirements for Build's isolated build environment, and `distro-base` identifies the minimal bootable package set. They use the common package-definition model; their detailed selection and dependency mechanics remain for subsequent Design.

## Progressive Decomposition

This document establishes ownership of package definitions, selection, dependency categories, and the no-package-specific-code requirement. Manifest syntax, list syntax and placement, condition expressions, build-step vocabulary, and resolution algorithms are deferred until required by bounded Functional Sets.
