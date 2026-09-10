# Package Metadata

## Purpose

This document defines the logical package metadata consumed by Manage and
published through the Package Database. It defines fields and invariants without
choosing the physical archive or metadata serialization.

Build is the producer of this metadata. Manage must not need Build recipes,
source locations, or other package-production state in order to resolve or apply
a package.

## Package metadata record

Each published package identity has one logical metadata record:

```text
package
    identity
        name
        version
        architecture
        revision

    depends[]
        name
        operator?
        version?

    conflicts[]
        name

    provides[]
        name
        version?

    owned_paths[]
```

`identity` is the concrete package identity defined by the Package Model:

```text
name + version + architecture + revision
```

`depends`, `conflicts`, and `provides` are runtime package relationships used by
Manage. `owned_paths` is the package's installed path inventory used for package
ownership, removal planning, conflict detection, and verification.

The archive format may later encode the path inventory separately from the
relationship metadata as long as they remain parts of the same logical package
record.

## Dependency record

A required dependency is represented as:

```text
name
operator?   one of = > >= < <=
version?
```

Package names and provided capability names share one global requirement
namespace, but a name has exactly one semantic kind.

```text
name
    -> package name
or
    -> capability name
never both
```

Once a name is established as a package name, no package may publish a
`provides` entry with that same name. Once a name is established as a capability
name, no package may be published with that name. Build must reject publication
that would create such a collision.

A dependency `name` therefore resolves unambiguously: a package-name requirement
is satisfied by that package, while a capability-name requirement is satisfied
by a package that provides that capability. The requirement kind also determines
which persistent ordered version registry is used for a version constraint.

An unconstrained dependency contains only `name`.

A constrained dependency must contain both `operator` and `version`. `version`
without an operator, or an operator without a version, is invalid metadata.

Examples:

```text
name: zlib
```

```text
name: ssl-api
operator: >=
version: 2
```

The comparison version must already exist in the appropriate persistent ordered
package or capability version registry. Manage never infers registry placement
from the version string.

## Conflict record

The initial conflict record contains only:

```text
name
```

The conflict name resolves through the same non-colliding global requirement
namespace as a dependency. A package-name conflict matches that package directly;
a capability-name conflict matches any package that provides that capability.

Version-constrained conflicts are outside the initial schema.

## Provide record

A provided capability is represented as:

```text
name
version?
```

Without `version`, the provide satisfies only an unversioned dependency on that
capability.

With `version`, the value must already exist in the persistent ordered registry
for that capability and may satisfy compatible versioned dependencies.

Capability version is independent of the provider package's own upstream
version.

## Installed-path record

The initial ownership schema records normalized target-root-relative paths:

```text
owned_paths[]
```

A package must not claim an absolute host path outside the selected target root.

Exact path normalization, directory ownership, intentional shared paths, mutable
configuration-file handling, and filesystem-drift policy remain later design
topics.

## Publication consistency

The Package Database publishes the same logical identity and relationship
metadata that Build associated with the selected package artifact.

Manage must resolve against published Package Database metadata before fetching
or applying package payloads. When applying an artifact, Manage must verify that
its embedded package identity and runtime relationship metadata agree with the
selected published record.

The exact mechanism for encoding or comparing the embedded metadata remains a
serialization decision; the semantic requirement is that Package Database
solver metadata and artifact metadata must not describe different packages.

## Installed-state projection

After successful application, Manage stores the package identity, runtime
relationships, verified artifact checksum, and owned paths in its installed
database together with local state such as install reason and hold state.

Build-only metadata is not copied into installed state.

## Undecided areas

- physical package archive format;
- physical metadata serialization;
- exact path normalization rules;
- directory and intentional shared-path ownership;
- mutable configuration-file policy;
- package-local lifecycle metadata and execution model;
- metadata schema-version migration policy.
