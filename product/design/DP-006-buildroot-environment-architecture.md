---
doc_id: DP-006
title: Buildroot Environment and Stage 1C Transition Architecture
depends_on:
  - DP-001
  - DP-002
  - DP-003
  - DP-004
  - DP-005
---

# Buildroot Environment and Stage 1C Transition Architecture

## Purpose

Stage 1C converts the verified Stage 1B temporary target-native filesystem into Distro's first published package collection capable of establishing its production package-construction environment. Stage 1C is a Bootstrap configuration of the existing Build engine, not a parallel engine or ongoing special package format. The produced `distro-buildroot` package collection becomes the source for subsequent production Build operations and Stage 2.

## Stage 1C input and operation

Stage 1C retains the command and stage ownership established by DP-002:

```sh
./product/scripts/build distro-buildroot \
  --root /path/to/rootdir \
  --cross-chroot /path/to/crosschrootartifact
```

Build must consume a matching, verified Stage 1B archive and completion metadata, safely restore it as a temporary construction root, and avoid dependency on the Stage 1B build workspace. The imported filesystem is a bootstrap input, not a collection of already-installed Manage packages. Its presence does not confer package ownership or allow its files to be silently reused as the published package payloads.

## Single production execution model

Stage 1C and normal package construction use the same **buildroot execution mode**: Build selects verified sources and recipes, prepares an isolated target-native construction environment, directly executes selected Bash recipes there, and stages each package's output separately for Manage. For Stage 1C only, the initial environment's source is the local verified Stage 1B filesystem because the corresponding Distro packages do not yet exist. Once available, the normal source is a Manage-resolved package collection. This changes the input provider, not the construction engine or its ownership.

The control-plane Build application may operate outside the isolated environment while the package-construction processes run inside it; placing the controller inside is not a product requirement. The execution contract must prevent undeclared foreign-host tools, runtime libraries and filesystem state from satisfying target-native construction requirements. The construction environment has deliberately bounded mounts, environment, writable build and staging locations, and fails closed when its required isolation cannot be established. The precise namespace technology and mount layout are Planning decisions.

## Native construction and package handoff

Stage 1C selects a distinct, explicit-version package list and directly executed Bash recipes using the shared manifests of DP-003. It builds the native package files required by the selected production environment. Every package is staged independently from the temporary construction root and from other package payloads. Build then calls the standard Manage creation/publication operations defined by DP-004 and elaborated by DP-005.

Package identities and manifest-derived dependencies are not reconstructed from the temporary root's directory contents. Rebuilding a package already represented by temporary Bootstrap files must not implicitly claim unrelated files or transfer their ownership. Build and Manage retain their separate duties throughout.

## Bootstrap closure and publication outcome

The `distro-buildroot` metapackage declares the intended production environment requirements through the authoritative package model. The published closure must contain the native tools, runtime libraries, headers, executable interpreters and other capabilities necessary to run the chosen Build construction workload, including dependencies needed by the Build executor where that executor runs. The exact package inventory, version selections and representative workload belong to Planning. The Stage 1B baseline alone does not establish this closure.

Stage 1C's product output is the initial Bootstrap package collection created and published through Manage. Stage completion additionally requires independent verification that the collection is installable into a fresh managed root and can establish an isolated production buildroot without importing undeclared files or tools from Stage 1B or the foreign host. An isolated candidate collection may be tested before it becomes the authoritative selectable collection; a successful test does not itself publish or accept the collection. Verification evidence establishes the completion gate and is not a separate package artifact, publication authority, or repository-governance acceptance record.

## Independent verification

Verification must distinguish:

1. **Bootstrap-input capability:** the verified Stage 1B environment can execute the selected native construction workload.
2. **Package correctness:** selected package artifacts have valid identity, integrity, dependency and ownership information and can be consumed independently by Manage.
3. **Production-environment closure:** a fresh root assembled from the complete `distro-buildroot` package closure can execute a representative native package build using the normal production Build environment-assembly and recipe-execution path, with no undeclared host userspace or temporary-bootstrap dependency. The test may use a candidate local package collection, but must use the same Manage-resolved package installation and Build execution behavior required for subsequent production builds, not a Stage 1C-only assembly or execution substitute.

Static dependency/ELF inspection supports the third condition but is not sufficient alone; representative execution is required. Tests must not claim that a successful Stage 1B handoff establishes full Stage 1C readiness or that one representative build establishes universal package buildability.

Stage 1C does **not** perform the final Distro-host generation-to-generation self-replication proof, construct `distro-base`, or install a bootable system. Those remain later Bootstrap and component responsibilities under DP-002.

## Failure and publication boundaries

A failed source verification, native construction, package creation, publication, dependency closure or independent managed-root test must not present Stage 1C as successfully completed. Published selections must remain internally consistent under failure as defined by DP-005. Stage 1C's completion result must distinguish packages merely constructed or staged from a verified, installable published collection.

## Progressive implementation

Planning may select smaller Functional Sets than the whole Stage 1C workflow, including a first end-to-end Build-to-Manage package slice, provided the slice uses the durable package and buildroot contracts rather than a throwaway implementation. There is no requirement to implement all Manage upgrade/removal behavior or the full later `distro-base` dependency graph merely to demonstrate the initial package-creation path.

The G1 package/Manage prototype and the package-closed buildroot/mount-namespace prototype are technical references to evaluate during Planning. Their discovery-driven selections, JSON command-language recipes, and direct Build-owned package writers are not adopted as Design authority.
