# Component Interfaces

## Purpose

Build, Manage, and Install are separate components. Their integration is
defined through explicit contracts rather than by exposing each component's
internal implementation to the others.

This document records the initial contracts that later design work must refine.

## Build to Manage: package artifact contract

Build produces package artifacts.

Manage consumes package artifacts.

The package artifact contract will eventually need to define at least:

- package identity;
- package version information;
- target architecture or compatibility information;
- installable filesystem payload;
- runtime package relationships;
- integrity information;
- package lifecycle metadata required for safe installation and removal.

This baseline does not choose the serialization or archive format.

## Install to Manage: target package-operation contract

Install must be able to request package operations against an installation
target rather than only against the currently running root filesystem.

The contract must preserve Manage as the authority for:

- applying package payloads;
- maintaining package records;
- checking package relationships and conflicts;
- executing any package lifecycle behavior that later design permits.

Install remains responsible for the surrounding installation workflow.

## Recipe versus package metadata

Build-time description and installed-package description are separate concepts.

A recipe may require information that is irrelevant after a package has been
built, such as source locations, source checksums, patches, build dependencies,
and build commands.

A package artifact needs only the information required for distribution,
validation, installation, package-state management, and later inspection.

The exact schemas remain undecided.

## Repository interface

A repository or distribution service may later sit between Build and Manage:

```text
Build --> package artifacts --> repository --> Manage
```

The presence of a repository does not change ownership:

- Build still owns package creation.
- Manage still owns package installation state.
- Install still uses Manage for package operations.

Repository metadata and transport are future design topics.

## Compatibility principle

The interfaces should permit each component to evolve independently as long as
the published contracts remain satisfied.

No component should require another component's private in-memory objects,
private database implementation, or build internals merely to perform its own
role.
