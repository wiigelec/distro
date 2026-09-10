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

Each accepted upstream version is assigned a distro-controlled `version_order`
key scoped to package name and shared across architectures.

The key is an exact rational number represented canonically as:

```text
numerator / denominator
```

where numerator is an arbitrary-precision signed integer, denominator is a
positive arbitrary-precision integer, and the fraction is reduced to lowest
terms.

For two versions of the same package, ordering is determined only by their
`version_order` values. Given `a/b` and `c/d` with positive denominators:

```text
a/b < c/d  iff  a*d < c*b
a/b = c/d  iff  a*d = c*b
a/b > c/d  iff  a*d > c*b
```

No floating-point conversion is permitted for version comparison.

The first accepted version of a package receives `0/1`. A version known to be
newer than every established version receives one greater than the greatest key.
A version known to be older than every established version receives one less
than the least key.

A version inserted between established versions `a/b < c/d` receives their
mediant:

```text
(a + c) / (b + d)
```

reduced to lowest terms. With positive denominators this key is strictly between
the two established keys, allowing insertion without renumbering existing
versions.

The pairwise ordering assigned to a published upstream version is immutable.
Ambiguous or non-monotonic upstream version schemes must therefore be resolved
before publication. Build may automatically place an ordinary clearly newer
upstream release after the greatest known version; an ambiguous ordering must
escalate for human review.

`version_order` is comparison metadata, not part of package identity. The
identity remains:

```text
name + version + architecture + revision
```

The explicit Package Database `current` identity is also independent of
`version_order`: distro policy may intentionally select a lower-ordered version
as `current`.

### Revision

`revision` identifies a corrected replacement build for the same
`name + version + architecture`.

Revision numbering is scoped to that tuple and increases monotonically when
human review determines that a replacement revision is required.

A recipe-file SHA change does not itself determine revision.

## Recipe Manifest binding

For each `name + version + architecture`, the Recipe Manifest stores the
currently accepted recipe-file SHA and current revision:

```text
name + version + architecture
    |
    +---- accepted recipe SHA
    |
    +---- current revision
```

The accepted SHA is a change detector and review anchor. It is not part of
package identity and does not autonomously determine revision.

Git history preserves previous recipe and Recipe Manifest states, so the live
Recipe Manifest does not need a separate audit-history structure.

## Recipe change review

Build compares the current recipe-file SHA to the accepted SHA in the Recipe
Manifest.

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
    -> keep revision
    -> store new SHA

accept with revision bump
    -> allocate next revision
    -> store new SHA

reject change
    -> restore prior recipe file from Git
    -> keep prior SHA and revision
```

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
- compare current recipe SHA with the accepted Recipe Manifest SHA;
- require human review on SHA mismatch;
- support exactly three outcomes: same revision, revision bump, or reject and
  restore;
- store the new SHA after either acceptance outcome;
- allocate the next revision only when review requires it;
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
