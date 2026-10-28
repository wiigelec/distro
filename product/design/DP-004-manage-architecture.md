---
doc_id: DP-004
title: Manage Architecture
depends_on:
  - DP-001
  - DP-003
---

# Manage Architecture

## Purpose

Manage creates and publishes Distro packages from Build-produced files and manages packages installed on target systems. Build is responsible for producing package file contents; Manage owns package assembly, metadata, publication, and installed-package state.

## Package Creation

```sh
./product/scripts/manage create --package package_name --build /path/to/build
```

`create` identifies the package with `--package` and assembles the files staged by Build under `--build` into a Distro package, including its package metadata. Manage uses dependency information originating from the authoritative manifests described in DP-003; it does not establish independent package dependency declarations.

Package archive format, metadata representation, and the precise staging interface remain open for subsequent Design.

## Package Publication

```sh
./product/scripts/manage publish --package package_name --repo /path/to/publish
```

`publish` publishes the created package identified by `--package` to the repository specified by `--repo`. Package repository format, addressing, transfer mechanism, and publication transaction remain open.

Creation and publication are separate Manage operations. The same interfaces apply to Bootstrap packages and subsequent production packages; the package-production workflow in Build may invoke both.

## Installed Package Management

Manage installs, removes, and upgrades packages on target systems and tracks their installed package state. Install invokes Manage to perform package installation when constructing a usable system. Detailed installed-package CLI forms, dependency resolution, state storage, and transaction rules remain open.

## Component Boundaries

Build fetches sources, executes configured builds, and stages the resulting package files. Manage does not compile sources or choose package-specific build instructions. Manage creates packages from the staged output, publishes packages, and applies installed-package operations. Install owns system assembly and configuration beyond package installation.

## Progressive Decomposition

This document establishes Manage's responsibilities and initial `create` and `publish` CLI contracts, not a complete package format or repository protocol. Such details may be specified as bounded Functional Sets require them.
