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

Manage consumes the architecture-scoped published Package Database defined by
[Package Database](package-database.md). For ordinary upgrade detection, Manage
compares an installed package identity with the explicit `current` identity in
that database. A different identity indicates an available package change.

The Package Database may also expose older published upstream versions for
explicit downgrade or version-selection operations. Superseded revisions of the
same upstream version are not normal downgrade targets because only the highest
published revision of each version is exposed.

## Target root

Manage must be designed so that package operations are not inherently tied to
the currently booted root filesystem.

This allows Install to populate a mounted target system using the same package
installation mechanism used for a running system. It may also allow Build to use
Manage when preparing a controlled build environment if later design chooses
that architecture.

The exact command-line spelling and target-root safety model are not yet
specified.

## Package-local lifecycle boundary

If package lifecycle behavior is later supported, Manage owns package-local
consequences of installing, upgrading, or removing a package.

Examples of the category include actions required to keep package-owned or
package-derived state coherent. The exact lifecycle model and permitted actions
are not yet specified.

Manage does not own installation-wide policy such as machine identity, user
choices, locale, networking policy, or other system configuration selected by
Install.

## Boundary with Build

Manage consumes package artifacts. It does not need package source or a build
recipe to install an already-created package.

Manage does not compile packages as part of normal package installation.

If Build later uses Manage to populate a build environment, that does not make
Manage responsible for dependency intent, build commands, compilation, staging,
or package creation.

## Boundary with Install

Install uses Manage to create package state in the target system.

Install may decide *which* packages belong in an installation, but Manage owns
the mechanics and records of installing those packages.

Manage owns package-local lifecycle consequences; Install owns
installation-wide machine policy and configuration.

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
- How are package hooks or lifecycle actions represented and constrained?
- How are repositories represented and authenticated?
- What integrity and signature checks are mandatory?
- What rollback or recovery behavior is required?
