---
doc_id: DP-003
title: Build Package Definitions and Selections
depends_on:
  - DP-001
  - DP-004
---

# Build Package Definitions and Selections

## Purpose

Build and Bootstrap share a user-maintained, configuration-driven package model consisting of **package manifests**, **package lists**, and **Bash recipes**. Package manifests define package identity and requirements; package lists select packages, explicit versions, and recipes; recipes contain the package-specific commands that construct and install files. Adding a package requires adding its configuration and recipe, not modifying Build application source code.

## Package Manifests — Static Definitions

Package manifests form one authoritative, user-maintained collection under `product/src/build/packages/`. The collection consists of multiple files, which users may organize in subdirectories by functionality or any other scheme. File organization does not determine package identity or behavior. Each package has one authoritative manifest, maintained independently of individual build requests.

Manifests are YAML files defining package identity and characteristics, including the package name, upstream project and release locations, source archive naming, source verification information, and dependencies. An archive name or URL may use `{version}`, resolved from the package list's selected version. Initially, sources are upstream release archives rather than Git checkouts. The manifest declares the verification scheme (such as SHA-256 or an applicable signature-verification method), not a checksum for any selected release. The package list owns version-specific expected checksum values or signature identities, which Build must verify before extraction. This division does not permit a list to redefine source locations, verification schemes, or dependencies.

**Manifests do not select versions, define version formats or discovery rules, or contain build instructions.**

The manifest collection is the **sole source of package dependency declarations**. Package lists and recipes do not add, replace, or override those declarations.

Dependencies have three categories:

- **Build tools:** needed to construct the package, but not required on the installed target solely because they were build tools.
- **Build link dependencies:** needed to construct the package and declared as requirements of the installed package.
- **Runtime dependencies:** needed by the installed package, regardless of whether they are needed during its construction.

Where dependency requirements vary with build context, that conditional meaning must be expressed by the manifest rather than redefined by a package list or recipe. The condition mechanism remains open.

## Package Lists — Explicit Build Selections

Package lists are user-maintained YAML files selecting packages, their **explicit versions**, corresponding version-specific verification values, and the Bash recipes to execute. A list references authoritative manifests rather than duplicating package identity, source descriptions, verification schemes, or dependency declarations. Version-specific checksums are selections, not manifest-source redefinitions. Version selections for dependencies are also supplied by the applicable package lists; the dependency relationships themselves remain defined only by manifests.

A representative entry is:

```yaml
packages:
  - name: binutils
    version: "2.47"
    recipe: binutils/cross-toolchain.sh
```

The selected version determines the version used to resolve source archive references from the manifest. For now, Build does not discover upstream releases, interpret version formats through manifest regexes, or support dynamic selectors such as `latest` or version-series expressions. Those capabilities may be considered later if needed.

Lists select the appropriate recipe for the build context; they do not contain the package's configure, make, installation, or other construction commands. The same manifest can be used by different lists with different recipes. For example, Binutils can have separate cross-toolchain, cross-chroot, and distro-buildroot recipes without duplicating its manifest.

Package-list storage is under `product/src/build/lists/`. Precise filename conventions, dependency-version resolution, and any optional list-level or recipe-specific parameters not yet demonstrated by a bounded Functional Set remain open.

## Package Recipes — Bash Build Instructions

Recipes are user-maintained **Bash scripts** under `product/src/build/recipes/`. Each recipe is selected by a package list and directly executed by Build. Recipes contain the ordered, package-specific operations needed to configure, compile, and install their package, including fixed compiler flags, configure options, patches, and cleanup where appropriate.

Recipes should remain straightforward to read, run, and modify, resembling the upstream or LFS construction instructions. Rather than requiring one heavily parameterized recipe to support every build context, separate recipes may hardcode the relevant build-context-specific options.

Build prepares the workspace and supplies a small standard execution context, including the extracted source directory, package build directory, installation root, and target triplet where applicable. The exact interface is subject to Functional Set definition. Recipes may use those standard values but should not require Build to parse their internal commands. A recipe is an ordinary Bash script and can be run independently when the required build context is provided.

**Build does not generate another script, translate a recipe language, or maintain a configurable command map.** It invokes the selected Bash recipe directly and records its outcome. The trusted, user-managed environment permits normal Bash recipes; a restricted command language is not a Design requirement.

## Host-Executed Build Isolation

Every Build operation that constructs package files using host-provided tools, including host-executed Bootstrap stages, shall execute its construction recipes within a controlled sandbox rather than in the unrestricted host environment. This host-execution isolation is distinct from the `distro-buildroot` production execution mode; it does not introduce a separate Build engine or a fourth product component.

The sandbox shall provide a deliberately defined construction environment: controlled environment variables, executable search paths, filesystem visibility, and explicitly designated writable build and installation locations. Required host tools and resources may be made accessible intentionally, but incidental host environment state shall not silently determine construction behavior.

Host system files and directories shall be protected against accidental modification by construction recipes. Absolute paths used during construction shall resolve to the intended sandbox-visible filesystem; package installation shall be confined to designated staging roots rather than the host system. If the required isolation cannot be established, Build shall fail rather than silently fall back to unrestricted host execution.

Bootstrap filesystem artifacts shall be usable after extraction into a different absolute host workspace location. A stable sandbox-visible target filesystem layout may be used to preserve toolchain path expectations without requiring the same host workspace path in successive stages. Portability means functional use after restoration, not merely successful archive extraction.

The sandbox technology, namespace and mount configuration, resource allowlist, exact environment contract, and verification mechanisms remain for bounded Planning and Build. Isolation protects against accidental host writes and environment leakage; it is not asserted to be a complete security boundary against malicious recipes.

## Execution and Component Boundaries

Build is one host-agnostic execution engine. It can run on a foreign Linux host (such as Arch) or on a Distro host. Invocation parameters select whether package construction uses host-provided tools in a controlled host-execution sandbox or runs inside an isolated environment established from `distro-buildroot`. For buildroot execution, CLI parameters select the source for constructing that environment: normally the package server, or the local Bootstrap artifact during Stage 1C. Host identity does not determine the execution mode.

Bootstrap is a special Build operation using the shared manifests, lists, and recipes, not a distinct package-building engine. Bootstrap Stages 1A and 1B execute using host-provided tools within the controlled host-execution sandbox. Stage 1C and normal publishable package construction execute inside `distro-buildroot`. Stage 1C selects a local Bootstrap artifact instead of package-server packages because the initial packages are not yet published. This changes the source for establishing the buildroot, not the Build engine or its execution mode.

Build resolves requirements from manifests, selects exact package versions and recipes from lists, acquires and verifies sources, prepares the execution context, executes recipes, and stages resulting package files. Package-specific construction commands belong in recipes, not in Build application code or package lists.

Build invokes Manage for package creation and publication. Manage assembles staged files into packages with metadata and publishes them through the interfaces defined in DP-004. This applies to Bootstrap and normal package builds. Manage derives dependency metadata from authoritative manifest information supplied by Build; it does not maintain an independent source of dependency declarations. Install uses Manage for package installation.

The `distro-buildroot` metapackage defines the requirements for Build's isolated build environment, and `distro-base` identifies the minimal bootable package set. They use the common package-definition model; their detailed selection and dependency mechanics remain for subsequent Design.

## Progressive Decomposition

This document establishes ownership of manifests, explicit versions in lists, independently selected Bash recipes, dependency categories, execution-environment selection, and the absence of package-specific instructions in Build application code. The exact YAML schemas, signature-verification mechanisms, recipe invocation interface, context-dependent dependency expressions, and dependency-version resolution mechanics may be refined for bounded Functional Sets. Dynamic version discovery and selection are deferred.
