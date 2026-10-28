---
doc_id: DP-003
title: Build Package Definitions and Selections
depends_on:
  - DP-001
  - DP-004
---

# Build Package Definitions and Selections

## Purpose

Build and Bootstrap use a shared, configuration-driven package model. Adding a package within the capabilities supported by Build requires creating or updating package manifests and appropriate package lists, not changing application source code. Package-specific configuration belongs exclusively to manifests and lists; Build supplies generic mechanisms to interpret and execute that configuration.

## Package Manifests — Static Definitions

Package manifests form one authoritative, user-maintained collection under `product/src/build/packages/`. The collection consists of multiple files, which users may organize in subdirectories by functionality or any other scheme. File organization does not determine package identity or behavior. A manifest is static in the sense that it describes the package independently of any particular build request; it remains user-editable.

Manifests define package identity and characteristics, including package name, upstream project URL, release URL, version formatting or interpretation, and dependencies. Manifests do not contain build instructions or build parameters. The manifest collection is the **sole source of package dependency declarations**. Package lists cannot add, replace, or override those declarations.

Dependencies have three categories:

- **Build tools:** needed to construct the package, but not required on the installed target solely because they were build tools.
- **Build link dependencies:** needed to construct the package and declared as requirements of the installed package.
- **Runtime dependencies:** needed by the installed package, regardless of whether they are needed during its construction.

Where dependency requirements vary with build context, that conditional meaning must be expressed by the package definition rather than redefined by a package list. The schema and condition mechanism remain open.

## Package Lists — Dynamic Build Selections

Package lists specify which packages a Build or Bootstrap operation requests and how to build them. They reference manifests rather than duplicating package definitions or dependency relationships. Lists determine version-selection strategies for requested packages **and their resolved dependencies**, together with all package-specific build instructions and parameters, including compiler flags, configure options, toolchain/target selection, and other build-context settings. Dependency version selections may be supplied by lists; they do not alter the dependency declarations in manifests.

Initially, version selections are fixed, explicit versions. Future Design may allow strategies including `stable`, `latest`, a version series such as `5.3`, and Bootstrap selections derived from the host environment. Version interpretation and release discovery use information supplied by manifests; version *selection* belongs to lists.

The same manifest can be used with different lists and build configurations. For example, GCC may be built as an initial cross-compiler, for a temporary bootstrap environment, and as a final native Distro compiler without creating separate GCC definitions or hardcoded GCC paths in Build's source.

Package-list storage location, file format, configuration precedence, version-strategy resolution, and list maintenance policy remain open.

## Execution and Component Boundaries

Build is one host-agnostic, configuration-driven execution engine. It can run on a foreign Linux host (such as Arch) or on a Distro host. Invocation parameters select whether package construction executes directly on the host or inside an isolated environment established from `distro-buildroot`. For a buildroot execution, CLI parameters also select the source for constructing that environment: normally the package server, or the local Bootstrap artifact during Stage 1C. Host identity does not determine the execution mode.

Bootstrap is a special Build operation controlled by Bootstrap-specific configuration, not a distinct package-building engine. It uses the same manifest/list model and generic Build capabilities. Bootstrap Stages 1A and 1B execute on the host. Stage 1C and normal publishable package construction execute inside `distro-buildroot`. The normal buildroot is established using packages obtained from the package server; Stage 1C instead selects a local Bootstrap artifact through Build CLI parameters because the initial packages are not yet published. This changes the source used to establish the buildroot, not the Build engine or execution mode. Stage 1C uses Manage to create and publish the initial Bootstrap package collection produced through this exception.

Build may provide generic support for build systems and operations, but must not require package-specific source-code changes to add a package expressible through those capabilities. Package-specific build instructions belong in lists, never in application code or manifests.

Build resolves build requirements from manifests and produces the staged package files. Build invokes Manage for package creation and publication. Manage assembles staged files into packages with metadata and publishes them through the interfaces defined in DP-004. This applies to Bootstrap and normal package builds. Manage derives dependency metadata from the authoritative manifest information supplied by Build; it does not maintain another source of dependency declarations. Install uses Manage for package installation.

The `distro-buildroot` metapackage defines the requirements for Build's isolated build environment, and `distro-base` identifies the minimal bootable package set. They use the common package-definition model; their detailed selection and dependency mechanics remain for subsequent Design.

## Progressive Decomposition

This document establishes ownership of package definitions, version selection for packages and dependencies, build instructions, execution-environment selection, dependency categories, and the no-package-specific-code requirement. Manifest syntax, list syntax and placement, condition expressions, build-step vocabulary, and resolution algorithms are deferred until required by bounded Functional Sets.
