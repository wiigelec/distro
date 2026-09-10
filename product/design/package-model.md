# Package Model

## Purpose

This document defines package identity and revision semantics before choosing a
physical archive format, metadata serialization, or recipe syntax.

## Package identity

A concrete package is uniquely identified by:

```text
name + version + architecture + revision
```

### Version

`version` identifies the upstream software version represented by the package.

Each newly accepted upstream version begins at `r1` for each architecture:

```text
foo 1.2 x86_64 r3
upstream -> 1.3
foo 1.3 x86_64 r1
```

The upstream `version` string is treated as an opaque package-identity value.
Manage does not infer ordering by parsing that string.

Each package name has a persistent distro-controlled ordered version registry
shared across architectures. It is global comparison state for the repository,
not independent architecture-local state.

Conceptually:

```text
foo:
    1.2
    1.3
    1.5
    2.0
```

The registry defines upstream-version ordering for that package. Manage does not
derive order from the upstream version string.

When Build accepts a newly observed upstream version, it inserts that version at
its correct position in the package's ordered registry. Existing entries keep
their relative order. Ambiguous or non-monotonic upstream version schemes must be
resolved before publication; an ambiguous placement escalates for human review.

Once a registry entry has appeared in published package metadata, it is a
permanent ordering anchor:

```text
published registry entry
    -> must not be deleted
    -> must not move across another established entry
```

New entries may be inserted before, after, or between established entries, but
the relative order of established entries is immutable.

Registry entries are persistent ordering anchors. They are not removed merely
because the corresponding package artifact is no longer available from the
Package Database.

This allows published dependency metadata such as `foo >= 1.3` to retain its
meaning even after `foo 1.3` is no longer installable.

The ordered registry is comparison authority, not part of package identity. The
identity remains:

```text
name + version + architecture + revision
```

The explicit Package Database `current` identity is also independent of registry
ordering: distro policy may intentionally select an earlier registry entry as
`current`.

A Package Database generation must expose one coherent copy of this global
comparison state to every architecture catalog in that generation. Architectures
may differ in package availability and `current` identity, but not in the
relative ordering of established package versions.

### Revision

`revision` identifies a corrected replacement build for the same
`name + version + architecture`.

Revision numbering is scoped to that tuple and increases monotonically when
human review determines that a replacement revision is required.

A recipe-file SHA change does not itself determine revision.

However, runtime package metadata is part of the package-management semantics of
a concrete identity. If a reviewed recipe change alters `depends`, `conflicts`,
`provides`, `owned_paths`, or later package-local lifecycle metadata for an
already accepted `name + version + architecture`, publication requires a new
revision.

## Build State recipe binding

For each `name + version + architecture`, Build State stores the currently
accepted recipe-file SHA and current revision:

```text
name + version + architecture
    |
    +---- accepted recipe SHA
    |
    +---- current revision
```

The accepted SHA is a change detector and review anchor. It is not part of
package identity and does not autonomously determine revision.

Git history preserves previous recipe and recipe-acceptance states, so Build
State does not need a second audit-history structure for recipe contents.

## Recipe change review

Build compares the current recipe-file SHA to the accepted SHA in Build State.

```text
stored SHA == current SHA
    -> no recipe review required

stored SHA != current SHA
    -> human review required
```

A mismatch blocks autonomous publication for the affected package version and
architecture until a human chooses exactly one outcome:

```text
accept same revision
    -> allowed only if runtime package metadata is unchanged
    -> keep revision
    -> store new SHA

accept with revision bump
    -> allocate next revision
    -> store new SHA

reject change
    -> restore prior recipe file from Git
    -> keep prior SHA and revision
```

If runtime package metadata differs from the metadata of the already accepted
identity, `accept same revision` is not a valid outcome. Review must either bump
the revision or reject the recipe change.

After either acceptance outcome, the newly accepted SHA becomes the baseline for
future comparisons.

## Build attempts and artifacts

Repeated build attempts do not create a new revision merely because they are
separate executions.

Build provenance such as timestamps, builder identity, and logs may distinguish
build attempts without changing package identity.

## Artifact integrity

Each published package artifact must have an integrity checksum.

The checksum verifies that the artifact obtained by Manage is the artifact
published for the selected package identity.

```text
package identity
    name + version + architecture + revision

artifact integrity
    checksum(package artifact)
```

The artifact checksum does not determine revision.

The checksum algorithm and representation remain undecided.

## Consequences for Build

Build must:

- determine `name`, `version`, `architecture`, and `revision`;
- start every newly accepted upstream version at `r1` per architecture;
- compare current recipe SHA with the accepted SHA recorded in Build State;
- require human review on SHA mismatch;
- support exactly three review outcomes: same revision, revision bump, or reject
  and restore;
- permit same-revision acceptance only when runtime package metadata is unchanged;
- require a revision bump before publishing changed runtime package metadata;
- store the new SHA after either acceptance outcome;
- allocate the next revision when review requires it;
- avoid revision changes merely for repeated build attempts;
- produce an integrity checksum for each published artifact.

## Consequences for Manage

Manage consumes the full package identity and compares installed identity with
the Package Database's explicit `current` identity for normal upgrade detection.

The Package Database exposes only the highest published revision for a given
`name + version + architecture`.

Manage must verify the published artifact checksum before applying the artifact,
subject to later integrity-policy design.

## Undecided areas

- package archive and filename formats;
- recipe syntax or serialization;
- exact allowed character grammar for opaque upstream version strings;
- architecture vocabulary and compatibility rules;
- exact revision allocation storage;
- whether revision numbering may contain gaps;
- artifact checksum algorithm and encoding;
- artifact provenance format;
- reproducibility guarantees;
- dependency metadata serialization.
