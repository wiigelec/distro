# Component Interfaces

## Purpose

Build, Manage, and Install are separate components. Their integration is
defined through explicit contracts rather than by exposing each component's
internal implementation to the others.

This document records the initial contracts that later design work must refine.

## Build to Manage: package artifact contract

Build produces package artifacts.

Manage consumes package artifacts.

Package identity is defined by the [Package Model](package-model.md) as:

```text
name + version + architecture + revision
```

The package artifact contract will eventually need to carry at least:

- the complete package identity;
- the machine-resolvable effective recipe identity bound to that revision;
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
- executing any package-local lifecycle behavior that later design permits.

Install remains responsible for the surrounding installation workflow and
installation-wide machine policy and configuration.

## Build to Manage: optional build-environment service

Later design may allow Build to use Manage to populate an alternate root or
other controlled build environment with packages needed for a build.

If that relationship is adopted:

- Build owns build dependency intent and the build process;
- Manage owns package-state changes inside the requested build environment;
- Manage does not interpret recipes or execute package builds;
- use of Manage by Build does not change the package artifact contract between
  them.

Whether this interface is actually used remains undecided.

## Recipe versus package metadata

Build-time description and installed-package description are separate concepts.

A recipe may require information that is irrelevant after a package has been
built, such as source locations, source checksums, patches, build dependencies,
and build commands.

A package artifact needs only the information required for distribution,
validation, installation, package-state management, and later inspection.

The exact schemas remain undecided.

## Repository interface

A repository or distribution service may sit between Build and Manage:

```text
Build --> package artifacts --> repository --> Manage
```

In this baseline, repository is an interface or distribution domain, not a
fourth primary component.

The presence of a repository does not change ownership:

- Build still owns package creation.
- Manage still owns package installation state.
- Install still uses Manage for package operations.
- Install may select or configure package sources for an installation without
  becoming responsible for repository consumption mechanics.

Repository metadata, publication, discovery, authentication, and transport are
future design topics.

## Configuration ownership

Package-local lifecycle behavior and installation-wide configuration are
different responsibilities.

Manage owns lifecycle consequences intrinsic to applying package-state changes.
Install owns machine-level choices and policy made as part of creating the
installed system.

The exact lifecycle mechanism and exact installation configuration model remain
undecided.

## Compatibility principle

The interfaces should permit each component to evolve independently as long as
the published contracts remain satisfied.

No component should require another component's private in-memory objects,
private database implementation, or build internals merely to perform its own
role.
