# Package Database

## Purpose

The Package Database is the authoritative published catalog of distro-built
packages available to Manage.

It is distinct from:

- the Package Manifest, which tells Build which upstream packages to track and
  where to discover or download their source;
- Build State, which records recipe acceptance, revision state, upstream
  observations, version decisions, build results, and other package-production
  facts;
- Manage's local installed-package database, which records what is installed on
  a target filesystem.

## Architecture scope

Package availability and `current` selection are architecture-dependent, while
requirement-name kind and version-comparison registries are repository-global.

The Package Database therefore publishes one coherent repository generation
containing global requirement/comparison state plus architecture-scoped catalogs:

```text
Package Database generation
    global requirements
        name
            kind: package | capability
            versions[]

    catalogs
        x86_64
        aarch64
        ...
```

The exact physical representation may use one file, several files, partitions,
or an equivalent structure. Regardless of representation, all parts belonging
to a generation form one atomic published snapshot.

Architecture remains part of concrete package identity as defined by the
[Package Model](package-model.md).

## Published package identities

The Package Database contains only package identities that have satisfied the
publication policy for that architecture.

A package that was detected, prepared, built, or validated but has not been
published must not become available to Manage merely because Build knows about
it.

Build State may therefore contain package identities or build attempts that are
absent from the Package Database.

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

The Package Database stores each package's persistent ordered version registry
in that package name's global requirement entry. The same upstream version has
the same registry position across architectures.

The registry is retained independently of the `available` set so that historical
versions used as dependency comparison anchors remain comparable even after their
artifacts are no longer installable.

Once an entry has appeared in published package metadata, it must remain in the
registry permanently and must retain its relative order with every other
established entry. New entries may be inserted without changing established
relative ordering.

Registry ordering does not select `current`; it exists for dependency
constraints, explicit version comparison, and classifying user-directed movement
between published versions.

## Logical database schema

The Package Database is published as a complete repository-wide generation. Its
logical structure is:

```text
package_database
    schema_version
    generation

    requirements
        name
            kind: package | capability
            versions[]

    catalogs
        architecture
            packages
                package_name
                    current
                        version
                        revision

                    available[]
                        version
                        revision
                        artifact_reference
                        artifact_checksum
                        metadata
                            depends[]
                            conflicts[]
                            provides[]
                            owned_paths[]
```

`generation` identifies one coherent published snapshot shared by every
architecture catalog in that snapshot.

`requirements` is the single global authority for requirement semantics. Each
entry permanently records whether the name is a `package` or `capability` and
contains that requirement's persistent ordered `versions` registry.

Once a requirement name appears, the entry is permanent and its kind is
immutable. Its version entries retain their established relative ordering. The
entry remains present even when no architecture catalog exposes the package or
any provider for the capability.

A package version therefore has the same registry position regardless of
architecture, and a capability version has the same position regardless of which
architecture provides it. An unversioned capability is represented naturally by
a capability requirement whose `versions` list is empty.

Each architecture catalog contains only architecture-dependent published state:
available identities and explicit `current` selection.

`current` identifies exactly one member of `available` when the package has any
available identity for that architecture.

Each `available` entry is one concrete package identity for its containing
architecture. It contains the artifact location, whole-artifact checksum, and
the solver/install metadata defined by [Package Metadata](package-metadata.md).

The schema intentionally does not duplicate package name or architecture inside
every nested field when those values are already supplied by the containing
records. A physical serialization may denormalize fields for convenience without
changing the logical model.

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

Publishing a higher revision for an already-published
`name + version + architecture` atomically replaces the previously exposed
revision for that version in `available`.

If the superseded identity was the package's `current` identity, `current` must
move atomically to the newly published higher revision. This preserves the
invariant that `current` is always a member of `available`.

Conceptually:

```text
available:
    1.2-r3
current:
    1.2-r3

publish 1.2-r4

available:
    1.2-r4
current:
    1.2-r4
```

This automatic current movement applies only to a higher revision of the same
upstream version that is already current. Publishing a different upstream
version does not by itself make that version current.

This rule reflects the meaning of revision as the distro's corrected or revised
package definition for the same upstream version and architecture.

## Current package identity

For each package and architecture that has one or more published available
package identities, exactly one of those identities must be designated as
`current`.

The `current` identity must be a member of the package's published `available`
set for that architecture.

`current` is an explicit publication decision. It must not be inferred merely by
choosing the numerically or lexically greatest available upstream version.

The exception is publication of a higher revision of the upstream version that
is already `current`: because the new revision replaces the superseded exposed
revision, `current` moves atomically to that replacement identity.

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

For ordinary upgrade behavior, Manage first refreshes its local Package Database
view and then synchronizes installed packages to the Package Database's explicit
`current` identity for the applicable package and architecture.

Conceptually:

```text
installed:
    zlib 1.3.1 x86_64 r2

current:
    zlib 1.3.1 x86_64 r3
```

The identities differ, so normal upgrade selects `1.3.1-r3`.

The same rule applies when `current` moves to an upstream version that compares
lower than the installed version:

```text
installed:
    foo 2.0-r1

current:
    foo 1.9-r4
```

Normal upgrade selects `1.9-r4` because `current` is authoritative distro state.
This synchronization is not classified as an explicit downgrade.

Manage does not need to independently assess upstream release ordering in order
to answer the ordinary question "is this installed package current?" or to
select the normal upgrade target.

Packages installed locally but lacking a published `current` identity are not
automatically removed by normal upgrade.

For dependency constraints and explicit version comparison, Manage uses the
persistent ordered version registry defined by the Package Model. Those ordering
semantics remain separate from normal `current` selection.

## Explicit downgrade behavior

An explicit downgrade is a user-directed selection of another published
non-current package version from the architecture-scoped Package Database. It is
separate from normal upgrade synchronization to `current`, even when normal
synchronization moves to a numerically or lexically lower upstream version.

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

Explicit downgrade participates in normal dependency resolution and hold
constraints. The exact user-confirmation policy remains undecided.

## Repository relationship

The Package Database is the metadata authority for published package selection;
the repository or distribution interface provides access to the package artifact
corresponding to a selected published identity.

The Package Database must carry or reference enough information for Manage to
locate the selected artifact and obtain the integrity checksum associated with
that published artifact.

The checksum used to verify the whole artifact is metadata external to the
artifact bytes being verified. It may live directly in Package Database
metadata or in repository metadata referenced by the Package Database.

The exact representation and checksum algorithm are not yet specified.

In the initial trusted-home-network deployment, the Package Database and
repository are expected to be hosted by the same authoritative Build server.
They may be physically combined or served as separate resources. That
implementation choice must not blur their semantic distinction:

```text
Package Database
    which published identity is selected or available

Repository
    how the selected package artifact is obtained
```

## Repository generations and publication consistency

Package Database publication and artifact availability use coherent generations
so Manage cannot observe newly published metadata that refers to artifacts that
were not yet made available.

Each published Package Database snapshot has one repository-wide monotonically
increasing `generation` value.

Publication follows this order:

```text
prepare generation N+1
    -> finalize all metadata
    -> make every newly referenced immutable artifact available
    -> verify every artifact reference and checksum
    -> publish generation N+1 as the current database generation
```

The switch that makes a new Package Database generation current must be atomic
from Manage's point of view. A client sees either the complete prior generation
or the complete new generation, including one coherent global requirement state and
all architecture catalogs belonging to that generation, never a partially
updated database.

A change to global requirement state therefore creates a new repository generation
even when package artifacts changed for only one architecture. An architecture
client selects its own catalog but always evaluates it against the global
requirements from that same generation.

Artifact references are immutable: once a generation associates an artifact
reference and checksum with a package identity, the bytes at that reference must
not change.

Every artifact referenced by a retained Package Database generation must remain
available for the lifetime of that retained generation.

A generation may be retired only as a complete metadata snapshot. Artifacts may
be garbage-collected only when no retained generation references them.

If Manage has a stale generation whose server-side snapshot has already been
retired before required artifacts are obtained, the transaction must fail
before payload mutation and refresh rather than silently substituting artifacts
from another generation.

The exact number or age of retained generations remains policy rather than a
schema requirement.

## Build publication relationship

Build owns package production and publication decisions.

Once a package identity is published into the Package Database, it becomes part
of the package catalog available to Manage.

The Package Database therefore represents published distro package state, while
Build State represents richer package-production and reconciliation state.

Conceptually:

```text
Package Manifest
    upstream tracking input
          |
          v
        Build
          |
          +----> Build State
          |
          +----> build and validation facts
          |
          v
      publication
          |
          v
Package Database generation
          |
          +----> global requirements
          |
          +----> architecture-scoped published identity selection
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

- physical Package Database serialization and indexing;
- whether architecture catalogs are separate files or logical partitions;
- repository transport or synchronization protocol;
- signature model and artifact-checksum algorithm;
- retention depth for older published upstream versions;
- how `current` is selected, approved, changed, or withdrawn;
- whether testing or staged publication channels exist;
- exact downgrade user-confirmation behavior;
- cache and refresh behavior in Manage.
