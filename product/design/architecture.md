# Architecture

## Purpose

The distro is organized around three primary components: **Build**, **Manage**,
and **Install**.

The components are separated by responsibility so that package creation,
package-state management, and system installation can evolve independently
while communicating through explicit contracts.

## Components

### Build

Build is the package builder and package-production authority.

At the individual package level, its responsibility is to turn source inputs
and a package recipe into one or more package artifacts suitable for
consumption by Manage.

At the distro level, Build is responsible for reconciling the Package
Manifest's maintainer-declared upstream-tracking configuration against recipe
state, upstream observations, package-production history, and published package
state according to package-specific automation policy. It may autonomously
schedule package work and escalate changes or failures that cannot be resolved
safely.

Build owns build-time and package-production state. It does not own the
installed state of a machine.

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

## Initial deployment model

The initial distro deployment target is a trusted home network.

One authoritative network server is expected to act as both the Build machine
and the host of the Package Database and package repository. Client systems use
Manage to consume the package state and artifacts published by that server.

Public mirrors, mirror ranking, repository federation, and decentralized package
publication are outside the initial design scope.

## Dependency direction

The intended package-production and installation relationships are:

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
 Repository
      |
      v
    Manage <--------- Install
      |                  |
      v                  v
 package state      system configuration
      \                  /
       \                /
        v              v
          target system
```

The repository in this diagram is an interface or distribution domain between
package production and package consumption. It is not established here as a
fourth primary component or executable.

Build and Manage meet at the package artifact contract.

Install orchestrates creation of a target system and depends on Manage as the
mechanism for populating and changing package state in that target. Install does
not sit in the package-production data path.

Manage does not depend on Install.

Manage does not depend on Build in order to install an already-created package.

Build may later use Manage as a package-state service when preparing an isolated
or alternate build environment. If it does, that operational dependency does
not transfer package-building responsibility to Manage.

## Design boundaries

The following boundaries are part of the initial design:

1. Build owns package creation and distro package-production reconciliation.
2. Manage owns installed package state.
3. Install owns installation orchestration.
4. Package installation logic belongs to Manage and is reused by Install.
5. Build may use Manage to populate a build environment without making Manage
   responsible for executing or defining builds.
6. Package-local lifecycle consequences belong to package management, while
   installation-wide machine policy and configuration belong to Install.
7. Build-time information and installed-package information may overlap, but
   neither component may assume that the other's internal representation is its
   own.
8. Cross-component behavior is defined through explicit interfaces rather than
   shared implementation assumptions.
9. A repository or distribution service may connect package production and
   consumption without becoming a primary component in this baseline.
10. The Package Manifest is desired-state authority for upstream package
    tracking; machine-maintained Build history and reconciliation state must not
    silently redefine that maintainer-declared configuration.
11. The repository-wide Package Database generation is authoritative published
    package state; its architecture catalogs define package identities available
    to Manage, and Build history is not a substitute for that published state.

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
