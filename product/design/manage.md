# Manage

## Role

Manage is the distro's package manager.

It is the authority for package state on a target filesystem.

## Responsibilities

Manage is responsible for package-state operations, including the following
categories of behavior as they are designed:

- installing package artifacts;
- removing installed packages;
- upgrading or replacing installed packages;
- querying installed package state;
- tracking package-owned files and metadata;
- enforcing package relationships and conflicts;
- validating package artifacts before applying them;
- maintaining the local package database or equivalent state store.

Repository access and dependency resolution may become Manage responsibilities,
but their detailed behavior is not yet specified by this baseline.

## Target root

Manage must be designed so that package operations are not inherently tied to
the currently booted root filesystem.

This allows Install to populate a mounted target system using the same package
installation mechanism used for a running system.

The exact command-line spelling and target-root safety model are not yet
specified.

## Boundary with Build

Manage consumes package artifacts. It does not need package source or a build
recipe to install an already-created package.

Manage does not compile packages as part of normal package installation.

## Boundary with Install

Install uses Manage to create package state in the target system.

Install may decide *which* packages belong in an installation, but Manage owns
the mechanics and records of installing those packages.

## Initial interface concept

At the architectural level:

```text
package artifact(s)
       |
       v
     Manage
       |
       +----> installed files
       |
       +----> authoritative package state
```

The package format, transaction model, dependency solver, repository protocol,
and package database implementation remain open design questions.

## Open design questions

- What is the installed package database model?
- Are operations transactional, and what does transactionality guarantee?
- How are dependencies represented and solved?
- How are file conflicts handled?
- How are package hooks represented and constrained?
- How are repositories represented and authenticated?
- What integrity and signature checks are mandatory?
- What rollback or recovery behavior is required?
