# Package Model

## Purpose

This document defines the semantic identity of a package before choosing a
physical package archive format, metadata serialization, or recipe syntax.

## Package identity

A concrete package is uniquely identified by four values:

```text
name + version + architecture + revision
```

Each value is part of package identity.

For example, these are distinct package identities:

```text
zlib 1.3.1 x86_64 r1
zlib 1.3.1 x86_64 r2
zlib 1.3.1 aarch64 r1
zlib 1.3.2 x86_64 r1
```

### Name

`name` identifies the packaged software or package unit.

The exact naming grammar and namespace rules are not yet specified.

### Version

`version` identifies the software version represented by the package.

The exact version grammar and ordering rules are not yet specified.

### Architecture

`architecture` identifies the target architecture of the package and
participates in package identity.

The supported architecture vocabulary and compatibility rules are not yet
specified.

### Revision

`revision` distinguishes distro package definitions for the same package name,
version, and architecture.

Revision is intentionally simple enough for human differentiation while still
being machine-resolvable. A human-facing representation uses an ordered integer
form such as:

```text
r1
r2
r3
```

Within a given `name + version + architecture`, revisions increase
monotonically as the effective recipe changes.

The exact storage type and formatting rules are not yet specified beyond this
semantic requirement.

## Recipe binding

A package revision is bound to one exact effective recipe identity.

Conceptually:

```text
name + version + architecture + revision
                         |
                         v
                    recipe_id
```

`recipe_id` is a machine-resolvable identifier for the effective recipe used to
define that package revision.

For a given `name + version + architecture + revision`, a different effective
recipe must not be accepted as the same package identity.

If the effective recipe changes, the package revision must change.

If the effective recipe does not change, rebuilding it does not by itself
create a new package revision.

## Effective recipe

The effective recipe is the recipe meaning that can affect the resulting
package definition or output.

It includes recipe-controlled inputs and behavior such as categories including:

- source declarations;
- patches;
- build commands;
- build or configure options;
- declared dependencies;
- recipe-controlled environment or build settings;
- included recipe fragments that affect recipe meaning.

A change that alters the effective recipe requires a new revision.

Changes that do not alter recipe meaning, such as comments or purely cosmetic
formatting, must not require a new package revision.

The exact rules for canonicalizing an effective recipe are not yet specified.

## Recipe identity

The recipe identity must be deterministic and machine-resolvable from the
effective recipe definition.

A content-derived identifier, such as a cryptographic hash of a canonical
effective recipe representation, is an expected implementation direction, but
the hashing algorithm, canonical representation, and encoded form are not yet
specified by this design.

The human-facing revision and the machine-facing recipe identity serve
different purposes:

```text
revision
    human differentiation and package ordering

recipe_id
    exact machine binding to the effective recipe definition
```

The revision therefore must not be treated as an unverified manual label. Build
must be able to establish that the revision being produced corresponds to the
effective recipe identity associated with that package definition.

## Build attempts and artifacts

Repeated build attempts using the same effective recipe do not create a new
package revision merely because they are separate build executions.

Build-specific provenance such as timestamps, builder identity, logs, output
checksums, or other artifact-level details may distinguish build artifacts
without changing package identity.

The exact provenance model and reproducibility requirements remain future
design topics.

## Consequences for Build

Build must:

- determine the package's `name`, `version`, `architecture`, and `revision`;
- determine the machine-resolvable identity of the effective recipe;
- bind the emitted package identity to that recipe identity;
- reject reuse of a package revision for a different effective recipe;
- avoid creating a new revision merely for another build attempt of the same
  effective recipe.

Build's revision authority is provided conceptually by the machine-maintained
Recipe Manifest defined by [Autonomous Build Runtime](autonomous-build.md).
That manifest preserves the mapping between package revisions and effective
recipe identities.

The exact mechanism by which Build allocates the next revision remains
undecided.

## Consequences for Manage

Manage consumes the full package identity:

```text
name + version + architecture + revision
```

Manage must be able to distinguish different revisions of the same package
name, version, and architecture.

For normal upgrade detection, Manage does not infer the newest package by sorting
versions and revisions. It compares installed identity with the explicit
`current` package identity published in the architecture-scoped
[Package Database](package-database.md).

The Package Database exposes only the highest published revision for a given
`name + version + architecture`, while Build history may retain superseded
revisions.

Version comparison semantics may still be required for dependency relationships,
explicit version selection, or downgrade policy. Architecture compatibility and
coexistence rules are also not yet specified.

## Undecided areas

This package model intentionally does not yet decide:

- package archive format;
- package filename format;
- recipe syntax or serialization;
- version grammar or comparison rules;
- architecture vocabulary or compatibility rules;
- how the next revision is assigned or published;
- whether revision numbering may contain gaps;
- canonical effective-recipe representation;
- recipe identity hash algorithm or encoding;
- artifact provenance format;
- reproducibility guarantees;
- dependency relationship semantics.
