# Package Database

## Purpose

The Package Database is the authoritative published catalog of distro-built
packages available to Manage.

It is distinct from:

- the Package Manifest, which tells Build which upstream packages to track and
  where to discover or download their source;
- the Recipe Manifest, which retains effective-recipe and revision history;
- Package History, which retains upstream observations and version-assessment
  decisions;
- Manage's local installed-package database, which records what is installed on
  a target filesystem.

## Architecture scope

Package Database state is architecture-dependent.

Conceptually, each supported architecture has an independent published catalog:

```text
Package Database
    x86_64
    aarch64
    ...
```

The exact physical representation may use separate databases, partitions, or an
equivalent architecture-scoped structure. The representation is not yet
specified.

Architecture remains part of concrete package identity as defined by the
[Package Model](package-model.md).

## Published package identities

The Package Database contains only package identities that have satisfied the
publication policy for that architecture.

A package that was detected, prepared, built, or validated but has not been
published must not become available to Manage merely because Build knows about
it.

Build and Recipe history may therefore contain package identities or build
attempts that are absent from the Package Database.

## Available versions

The Package Database may expose multiple published upstream software versions of
the same package so that Manage can perform an explicit downgrade or install a
non-current published version.

Conceptually:

```text
zlib
    current: 1.3.2-r1
    available:
        1.3.2-r1
        1.3.1-r3
        1.2.13-r4
```

The exact schema and retention depth for older published versions are not yet
specified.

## Highest revision per version

For a given `name + version + architecture`, the Package Database exposes only
the highest published revision.

Conceptually, if Build history contains:

```text
zlib 1.3.1 x86_64 r1
zlib 1.3.1 x86_64 r2
zlib 1.3.1 x86_64 r3
```

then the Package Database exposes:

```text
zlib 1.3.1 x86_64 r3
```

and does not normally expose `r1` or `r2` as selectable package identities.

Superseded revisions remain Build/history information rather than normal
published downgrade targets.

This rule reflects the meaning of revision as the distro's corrected or revised
package definition for the same upstream version and architecture.

## Current package identity

For each package and architecture that has one or more published available
package identities, exactly one of those identities must be designated as
`current`.

The `current` identity must be a member of the package's published `available`
set for that architecture.

`current` is an explicit publication decision. It must not be inferred merely by
choosing the numerically or lexically greatest available version.

Conceptually:

```text
available:
    2.0-r1
    1.9-r4

current:
    1.9-r4
```

is valid if distro publication policy intentionally keeps `1.9-r4` as current.

A package with no published identity for an architecture has no `current`
identity for that architecture. Withdrawal, staged publication, or other future
states must be modeled explicitly rather than represented accidentally by an
incomplete published catalog.

The exact mechanism used to select, change, or withdraw `current` remains future
design.

## Manage upgrade behavior

For ordinary upgrade detection, Manage compares the installed package identity
with the Package Database's explicit `current` identity for the applicable
package and architecture.

Conceptually:

```text
installed:
    zlib 1.3.1 x86_64 r2

current:
    zlib 1.3.1 x86_64 r3
```

The identities differ, so a package change is available.

Manage does not need to independently assess upstream release ordering in order
to answer the ordinary question "is this installed package current?"

Manage may still require version comparison semantics later for dependency
constraints, explicit version selection, downgrade policy, or other package
operations. Those semantics remain separate from normal current-package
detection.

## Explicit downgrade behavior

An explicit downgrade selects another published package version from the
architecture-scoped Package Database.

Because only the highest revision of each version is exposed, an explicit
downgrade moves between published upstream versions rather than to a superseded
revision of the same version.

For example:

```text
1.3.2-r1
    |
    v
1.3.1-r3
```

may be a valid downgrade if both identities remain published.

Whether dependency resolution, confirmation, or additional safety policy is
required for downgrade remains undecided.

## Repository relationship

The Package Database is the metadata authority for published package selection;
the repository or distribution interface provides access to the package artifact
corresponding to a selected published identity.

The Package Database may carry or reference enough information for Manage to
locate that artifact, but the exact representation is not yet specified.

The Package Database and repository metadata may eventually be physically
combined, distributed together, or served separately. That implementation
choice must not blur their semantic distinction:

```text
Package Database
    which published identity is selected or available

Repository
    how the selected package artifact is obtained
```

## Build publication relationship

Build owns package production and publication decisions.

Once a package identity is published into the Package Database, it becomes part
of the package catalog available to Manage.

The Package Database therefore represents published distro package state, while
the Recipe Manifest and Build runtime state represent richer package-production
history.

Conceptually:

```text
Package Manifest
    upstream tracking input
          |
          v
        Build
          |
          +----> Recipe Manifest / Build history
          |
          +----> build and validation state
          |
          v
      publication
          |
          v
Package Database (architecture scoped)
          |
          +----> published identity selection
          |
          v
        Manage
          |
          v
 Repository / distribution interface
          |
          v
   selected package artifact
```

## Undecided areas

This design intentionally does not yet decide:

- Package Database file format or serialization;
- whether architecture catalogs are separate files or logical partitions;
- repository transport or synchronization protocol;
- signature and integrity model;
- retention depth for older published upstream versions;
- how `current` is selected, approved, changed, or withdrawn;
- whether testing or staged publication channels exist;
- exact downgrade transaction behavior;
- dependency constraints involving non-current versions;
- cache and refresh behavior in Manage.
