# Architecture

## Purpose

The distro is organized around three primary components: **Build**, **Manage**,
and **Install**.

The components are separated by responsibility so that package creation,
package-state management, and system installation can evolve independently
while communicating through explicit contracts.

## Components

### Build

Build is the package builder.

Its responsibility is to turn source inputs and a package recipe into one or
more package artifacts suitable for consumption by Manage.

Build owns build-time concerns. It does not own the installed state of a
machine.

### Manage

Manage is the package manager.

Its responsibility is to install, remove, upgrade, query, and otherwise manage
packages on a target filesystem while maintaining authoritative package state.

Manage owns package installation state. It does not build source packages.

### Install

Install is the system installer.

Its responsibility is to create a usable installed system by preparing a target,
using Manage to populate that target with packages, and performing the
system-level configuration required for installation.

Install does not implement a second package installation mechanism.

## Dependency direction

The intended dependency direction is:

```text
source + recipe
      |
      v
    Build
      |
      v
 package artifacts
      |
      v
    Manage <----- Install
      |
      v
installed package state
```

Build and Manage meet at the package artifact contract.

Install depends on Manage as the mechanism for populating and changing package
state in the target system.

Manage does not depend on Install.

Manage does not depend on Build in order to install an already-created package.

## Design boundaries

The following boundaries are part of the initial design:

1. Build owns package creation.
2. Manage owns installed package state.
3. Install owns installation orchestration.
4. Package installation logic belongs to Manage and is reused by Install.
5. Build-time information and installed-package information may overlap, but
   neither component may assume that the other's internal representation is its
   own.
6. Cross-component behavior is defined through explicit interfaces rather than
   shared implementation assumptions.

## Undecided areas

This baseline intentionally does not yet decide:

- implementation language;
- package archive format;
- package recipe format;
- repository format;
- dependency expression syntax;
- package database implementation;
- transaction and rollback semantics;
- build isolation mechanism;
- installer user interface;
- bootloader policy;
- filesystem layout beyond what later design requires.

Those decisions should be made incrementally as the design is refined.
