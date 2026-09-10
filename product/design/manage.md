# Manage

## Role

Manage is the distro's package manager and the authority for package state on a
target filesystem.

Its operational model should be simple and transactional in the same general
spirit as pacman: one package-management component handles installation,
removal, upgrades, repository refresh, queries, dependency resolution, package
verification, and package-state recording. This is a design influence, not a
requirement to copy pacman's CLI, database format, version semantics, or
implementation.

## Deployment context

The initial distro deployment model is a trusted home network with one
authoritative server that is both the Build machine and the host of the Package
Database and package repository.

Manage clients consume package metadata and artifacts from that server. Public
mirrors, mirror ranking, repository federation, and decentralized package
publication are outside the initial design scope.

The Package Database and repository remain semantically distinct even though
they are expected to be colocated on the same server.

## Responsibilities

Manage is responsible for:
- refreshing its local view of the authoritative Package Database;
- resolving requested package operations;
- installing, removing, upgrading, replacing, downgrading, and reinstalling
  package artifacts;
- querying installed and published package state;
- tracking package-owned files and installed metadata;
- recording why a package is installed;
- resolving runtime package relationships and conflicts;
- verifying package artifact integrity before applying an artifact;
- planning and applying package transactions;
- maintaining the authoritative installed-package database for the target root.

## Installed package state

For each installed package, Manage records enough state to identify both the
logical package release and the exact artifact that was applied.

At minimum, the installed record conceptually includes:

```text
name
version
architecture
revision
artifact checksum
install reason
hold state
owned files
package metadata required for dependency and removal operations
```

The complete package identity remains:

```text
name + version + architecture + revision
```

The artifact checksum is not part of package identity. It records which exact
published artifact bytes were installed.

Build-only information such as recipe SHA, source locations, upstream
observations, and package-production history does not belong in Manage's
installed-package database.

## Installed database schema

Manage's installed database is target-root-local authoritative package state.

Its logical top-level structure is:

```text
installed_database
    schema_version
    packages[]
```

Each installed package record contains:

```text
identity
    name
    version
    architecture
    revision

artifact_checksum
install_reason       explicit | dependency
held                 true | false

depends[]
conflicts[]
provides[]
owned_paths[]
```

The relationship and path fields are the installed-state projection of the
logical [Package Metadata](package-metadata.md) record used when the package was
applied. Keeping them locally allows dependency resolution, removal, ownership
queries, and orphan analysis without requiring the package to remain available
from the repository.

`artifact_checksum`, `install_reason`, and `held` are Manage state and are not
part of package identity.

The initial installed-state model permits at most one installed identity for a
given package name in a target root. Replacement, upgrade, downgrade, and
reinstall therefore update that package's installed record rather than creating
side-by-side versions of the same package name.

The physical database format, indexing strategy, locking mechanism, and
crash-recovery representation remain implementation decisions.

## Install reason

Manage records whether a package was installed because it was directly requested
or because it was needed as a dependency.

The initial semantic values are:

```text
explicit
dependency
```

This distinction supports identifying dependency-installed packages that are no
longer required by any installed package.

If a package already recorded as `dependency` is explicitly requested by the
user, Manage promotes its install reason to `explicit` even when no package
payload change is required.

Manage must also permit an explicit administrative operation that changes an
installed package's reason from `explicit` back to `dependency`. That operation
changes package-management state; it does not itself remove the package.

Being an orphan does not itself authorize automatic removal.

## Package Database refresh

Refreshing package metadata and changing installed packages are separate
operations.

```text
refresh
    -> obtain current authoritative Package Database state
    -> update Manage's local metadata view
    -> do not modify installed package state
```

The exact refresh command, transport, cache format, and stale-data policy remain
undecided.

## Package-state comparison

For ordinary current-package detection, Manage compares the installed package
identity with the Package Database's explicit `current` identity.

```text
installed identity == current identity
    -> current package identity

installed identity != current identity
    -> package identity change available
```

Manage should additionally classify useful special cases without requiring
upstream-version ordering merely to answer whether a package is current:

```text
same version, different revision
    -> replacement revision available

different upstream version
    -> different published version selected as current

installed identity absent from Package Database
    -> installed package unavailable from current published catalog

same identity, installed checksum differs from published checksum
    -> same package identity, different artifact
```

An installed package absent from the current Package Database is not
automatically removed.

A same-identity checksum difference is not an upgrade because package identity
has not changed. It is reportable state that may be resolved by an explicit
reinstall, repair, or later policy.

## Upgrade behavior

A normal system upgrade is an authoritative synchronization operation.

`upgrade` first refreshes Manage's local Package Database view, then synchronizes
installed packages to the refreshed Package Database's explicit `current`
identities.

Conceptually:

```text
upgrade
    |
    v
refresh local Package Database view
    |
    v
compare installed packages with explicit current identities
    |
    v
resolve required dependency changes
    |
    v
prepare transaction
    |
    v
apply transaction
```

If an installed package has a different identity from the refreshed `current`
identity, normal upgrade selects that `current` identity regardless of numerical
or lexical upstream-version direction.

For example:

```text
installed:
    foo 2.0-r1

current:
    foo 1.9-r4

upgrade:
    foo 2.0-r1 -> foo 1.9-r4
```

This is a normal synchronization to distro `current`, not an explicit downgrade
operation.

Manage does not need to infer the newest upstream release to perform ordinary
upgrade selection because the Package Database explicitly designates `current`.

An installed package that has no `current` identity in the refreshed Package
Database is not automatically removed by `upgrade`.

A held package is immutable package state until it is explicitly unheld.
Normal synchronization, dependency resolution, orphan cleanup, reinstall,
replacement, explicit version selection, and removal must not change or remove
a held package.

Version ordering does not participate in normal synchronization to Package
Database `current`. It is used only where explicit comparison is required,
including dependency constraints and explicit version selection.

## Explicit version selection and downgrade

A user may explicitly request another available identity from the Package
Database.

An explicit downgrade is a user-directed selection of a published non-current
identity that represents an older upstream version than the selected installed
or current package state. It is distinct from normal `upgrade`, which always
synchronizes to the Package Database's explicit `current` identity even when that
moves the installed upstream version downward.

Manage must not select superseded revisions of the same upstream version because
the Package Database exposes only the highest published revision of each
available version.

Explicit installation or downgrade to a non-current published identity does
not implicitly create a hold. Unless the package is separately held, a later
normal `upgrade` synchronizes it back to Package Database `current`.

Explicit downgrade participates in the same dependency and hold constraints as
other package-changing transactions.

## Reinstall and same-identity replacement

Manage must support explicitly reapplying the artifact associated with a selected
published identity even when that identity is already installed.

Typical reasons include repairing damaged package-owned files or replacing an
installed artifact whose recorded checksum differs from the currently published
artifact for the same identity.

A reinstall does not create a new package identity.

## Transaction model

Package-changing operations are transaction-oriented.

Before modifying the target filesystem, Manage must resolve the complete planned
operation sufficiently to determine at least:
- packages to install;
- packages to remove;
- packages to replace;
- selected published identities;
- required dependency changes;
- provider selections;
- held-package constraints;
- package relationship conflicts;
- package-owned file conflicts detectable before application;
- required artifacts and expected checksums.

```text
request
   |
   v
resolve
   |
   v
transaction plan
   |
   +---- installs
   +---- removals
   +---- replacements
   +---- dependency consequences
   +---- conflicts
   |
   v
validate
   |
   v
apply
   |
   v
update installed-package database
```

A transaction that cannot be resolved or validated must fail before ordinary
payload application begins.

Before application, Manage should be able to present the resolved transaction
plan including explicit changes and dependency-induced installs, removals,
replacements, provider changes, and requested orphan cleanup.

Stronger guarantees such as rollback after partial filesystem mutation or
interruption remain undecided.

## Artifact verification

Before applying a repository artifact, Manage verifies its whole-artifact
checksum against the checksum supplied by authoritative Package Database or
repository metadata.

The installed package record stores the verified artifact checksum.

Checksum verification establishes artifact integrity, not independent
authenticity of an untrusted publisher. The initial trusted-LAN deployment does
not require a public-distribution signature hierarchy.

## File ownership and conflicts

Manage owns the record of files installed by packages.

Package installation, removal, replacement, and verification must use this
ownership information. A transaction must detect package-owned path conflicts
that can be determined before applying conflicting payloads.

Intentional shared files, directory ownership, mutable configuration files, and
filesystem drift remain undecided.

## Orphans and obsolete dependency cleanup

A dependency-installed package is an orphan when no installed package currently
requires it under the dependency model.

Manage must be able to query and report orphaned packages.

A package recorded with install reason `explicit` is not considered an orphan
merely because no installed package depends on it.

Orphan status alone does not cause automatic removal during a normal `upgrade`.

Manage must provide an explicit orphan-cleanup operation through the normal
transaction model.

Orphan cleanup is resolved as a closure against the planned resulting installed
state rather than as a one-pass removal of only the packages that are orphaned
before the transaction begins.

For example:

```text
A explicit
└── B dependency
    └── C dependency

A no longer requires B

B becomes orphaned
removing B means C is no longer required
cleanup transaction removes B and C
```

Conceptually:

```text
orphans
    -> report currently orphaned dependency-installed packages

remove-orphans
    -> resolve full removable orphan closure
    -> remove that closure in one transaction
```

A combined upgrade-and-clean operation computes cleanup against the planned
post-upgrade dependency graph:

```text
upgrade --clean
    -> refresh Package Database
    -> synchronize non-held installed packages to current
    -> resolve the planned post-upgrade installed state
    -> compute the full orphan closure in that resulting state
    -> include those orphan removals in the same transaction
```

Held packages are excluded from the removable orphan closure. If a held package
would otherwise be orphaned, it remains installed.

The exact CLI spelling remains undecided. The semantic requirement is that normal
upgrade does not silently remove orphaned dependencies, while cleanup can be
requested explicitly either as a separate operation or as part of an
upgrade-and-clean transaction.

## Holds

Manage supports a simple per-package hold state.

A hold is a hard local constraint: Manage must not change or remove a held
package until the hold is explicitly removed.

Conceptually:

```text
not held
    -> package may participate normally in resolved transactions

held
    -> retain installed identity
    -> do not reinstall or replace
    -> do not remove
    -> exclude from orphan cleanup
```

A hold does not alter Package Database state, package identity, artifact
identity, or install reason. It is local Manage policy attached to installed
package state.

If satisfying a requested transaction would require changing or removing a held
package, dependency resolution fails before filesystem mutation. The error should
identify the held package as a blocking constraint.

For example:

```text
foo current requires libbar >= 3

installed:
    libbar 2.5 held

upgrade:
    -> no valid solution while preserving hold
    -> dependency-resolution error
    -> no filesystem mutation
```

A held package can be made mutable only by explicitly removing its hold first.
There is no implicit or explicit-operation bypass of an active hold.

Installing an explicit non-current version does not automatically create a hold,
and creating a hold does not itself select or install another version.

Manage must support operations equivalent to:

```text
hold
unhold
list holds
```

The exact CLI spelling remains undecided. A broader pinning or preference system
is outside this initial model.

## Dependency relationships

The initial dependency model intentionally stays small.

Package metadata may express:

```text
depends
conflicts
provides
```

`depends` declares a required package name or provided capability, optionally
with a version constraint.

`conflicts` declares package names or provided capabilities that must not coexist
in the resulting installed state.

A conflict naming a capability matches any package that provides that
capability. A conflict naming an actual package matches that package directly.

`provides` declares additional capability names that an installed package can
satisfy for dependency resolution.

Package names and capability names share one global persistent requirement
namespace, but the same name must not be both a package name and a capability
name. Published metadata that would create such a collision is invalid and must
not participate in resolution.

Manage interprets dependency and conflict names using the requirement namespace
from the same Package Database generation as the architecture catalog being
resolved. Namespace entries remain authoritative even when the named package or
all providers of a capability are no longer available.

This invariant makes every dependency or conflict name unambiguous before
provider selection or version comparison: package-name requirements use the
package's ordered version registry, while capability-name requirements use the
capability's ordered version registry.

A provided capability may be unversioned or may advertise an explicit capability
version. Capability version is independent of the provider package's own upstream
version.

Each versioned capability uses a persistent ordered capability-version registry
scoped to capability name.

An unversioned provide satisfies only an unversioned dependency on that
capability. A versioned dependency on a capability requires a provider that
advertises a capability version whose position in the capability registry
satisfies the requested constraint.

Optional or suggested dependencies are outside the initial dependency model and
may be added later without changing the meaning of required dependencies.

## Dependency version constraints

The initial constraint language supports comparisons equivalent to:

```text
=
>
>=
<
<=
```

An unconstrained dependency requires only that some acceptable package or
provider satisfying the named requirement be present.

Package-version ordering uses the Package Model's persistent ordered version
registry. Manage must not parse or heuristically order the opaque upstream
`version` string.

For package-name dependencies, the comparison target must be an established
version entry in that package's registry. If the dependency names a comparison
version that is absent from the registry, the package metadata is invalid for
resolution and the transaction fails before filesystem mutation. Manage must not
guess where an unknown version belongs by parsing its string.

The same rule applies to versioned capability dependencies: the comparison
capability version must already exist in that capability's persistent ordered
registry.

The operators have these semantics:

```text
=   exact upstream version match
>   registry position after target version
>=  exact version match or registry position after target
<   registry position before target version
<=  exact version match or registry position before target
```

Revision is not independently constrained by the initial dependency language.
For an available upstream version, Manage uses the Package Database's exposed
highest published revision for that version.

A dependency bound remains comparable even when its target version is no longer
installable because registry entries persist independently of repository
availability.

## Solver invariants

Manage resolves package-changing requests against the complete planned resulting
installed state before ordinary filesystem mutation.

The solver must simultaneously satisfy:

```text
explicit user request
Package Database selections
held installed-package constraints
required dependencies
version constraints
conflicts
provider choices
removal safety
```

A transaction has no valid solution if any required dependency would be
unsatisfied, any conflict would remain, or satisfying the request would require
changing or removing a held package.

An unresolvable transaction fails before ordinary filesystem mutation and should
report the constraints that prevented a solution.

The solver must not silently override a hold, leave an unsatisfied dependency, or
ignore a declared conflict merely to complete a requested operation.

## Provider selection and stability

A package-name dependency is satisfied by the named package itself. A
capability-name dependency is satisfied by a package whose metadata declares a
matching `provides` capability. The global non-collision invariant prevents one
requirement name from having both interpretations.

When multiple valid providers exist, Manage should prefer an already-installed
valid provider rather than switching providers without a reason.

Conceptually:

```text
app depends on ssl-provider

installed:
    openssl provides ssl-provider

available:
    openssl provides ssl-provider
    libressl provides ssl-provider

normal resolution:
    -> retain openssl if it still satisfies all constraints
```

Provider replacement is allowed when required by the explicit request,
dependency constraints, conflicts, repository state, or another hard solver
constraint.

When multiple valid providers remain, Manage selects deterministically in this
order:

```text
1. retain an already-installed satisfying provider
2. otherwise prefer a satisfying provider whose package identity is Package
   Database current
3. otherwise choose the lexically smallest package name
```

If more than one candidate remains for the same package name after those rules,
the solver uses the selected published package identity required by the
transaction and Package Database state rather than incidental iteration order.

Provider selection must therefore be deterministic and must not depend on
repository traversal order or internal collection ordering.

Dependency cycles are not inherently invalid. A cycle such as `A depends B` and
`B depends A` may resolve successfully when the complete planned resulting state
satisfies every dependency, conflict, provider, and hold constraint. Manage must
resolve the complete set rather than require dependencies to become valid one
package at a time during planning.

## Removal safety

Removing a package must be resolved against the complete resulting dependency
graph.

A requested removal fails if an installed package would have an unsatisfied
required dependency afterward, unless the same transaction explicitly removes
or replaces the dependent package or otherwise provides a valid dependency
solution.

Conceptually:

```text
A depends on B

remove B
    -> fail while A remains and no replacement satisfies B

remove A + B
    -> may resolve successfully
```

Held packages remain immutable during removal resolution. If a valid removal
transaction would require changing or removing a held package, resolution fails.

## Target root

Manage must not be inherently tied to the currently booted root filesystem.

The same transaction and installed-state model must work against an explicitly
selected target root. This allows Install to populate a mounted target system
using Manage and may later allow Build to provision controlled build roots.

## Package-local lifecycle boundary

If package lifecycle behavior is supported, Manage owns package-local
consequences of installing, replacing, or removing a package.

Manage does not own installation-wide policy such as machine identity, user
choices, locale, networking policy, or boot configuration selected by Install.

Lifecycle execution must participate in the package transaction model rather
than become a separate package installation mechanism.

## Boundary with Build

Manage consumes published package identities and artifacts. It does not need
package source or recipes to install an already-built package.

If Build later uses Manage to provision a controlled build environment, Manage
remains responsible only for package-state changes in that target.

## Boundary with Install

Install uses Manage to create package state in the target system.

Install may decide which packages belong in an installation, but Manage owns the
transaction mechanics, artifact verification, file ownership, and installed
records.

## Initial command model

The exact CLI remains undecided, but the design favors explicit operation names
rather than requiring pacman-compatible flag syntax.

Conceptually, Manage should support operations equivalent to:

```text
refresh
install
remove
upgrade
upgrade with orphan cleanup
search
info
list/query
verify
reinstall
explicit version selection / downgrade
hold / unhold / hold query
install-reason change
orphan query
orphan removal
```

## Open design questions

- exact installed package database serialization and storage layout;
- exact deterministic provider tie-break rule when installed-state preservation
  does not select a unique provider;
- transaction guarantees after filesystem mutation begins;
- mutable configuration-file behavior during upgrades;
- intentional shared-file and path-replacement semantics;
- package-local lifecycle representation and constraints;
- repository transport on the home network;
- downloaded-artifact cache policy;
- rollback or recovery after interruption.
