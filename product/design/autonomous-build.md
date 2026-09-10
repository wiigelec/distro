# Autonomous Build Runtime

## Purpose

Build is not limited to executing a single package recipe on demand.

The distro design expects Build to evolve into an autonomous package-production
runtime that maintains packages according to maintainer-declared upstream
tracking configuration by reconciling package policy, recipe state, upstream
observations, package-production history, and published package state.

This document defines that architectural direction without choosing the runtime
implementation, scheduler, polling mechanism, manifest serialization, or alert
transport.

## Reconciliation model

At the architectural level, Build operates as a reconciler:

```text
upstream tracking configuration
      |
      v
Package Manifest
      |
      v
 Build Runtime <--------- upstream observations
      |
      +----> Recipe Manifest
      |
      +----> Package History
      |
      +----> build scheduling
      |
      +----> package production
      |
      +----> validation
      |
      +----> publication state
      |
      +----> Package Database
      |
      +----> escalation when automation cannot proceed safely
```

The runtime compares maintainer-declared upstream tracking configuration with
observed and historical package-production state and performs the work needed to
keep published distro packages reconciled with that configuration and policy.

Autonomy is policy-driven and package-specific. The design does not assume that
every package can be updated with the same level of automation.

## Package Manifest

The Package Manifest is Build's maintainer-declared upstream-tracking input for
the distro package set.

At minimum, it identifies the package names Build is expected to track and the
upstream location or discovery information needed to query and download source.
It may also carry package-specific automation policy and other upstream-tracking
configuration as later design requires.

Conceptually, it answers:

```text
What packages do we track, and where does Build look upstream for them?
```

The exact fields and serialization remain undecided.

The Package Manifest is desired-state authority for upstream package tracking.
Machine-maintained Build state must not silently add or remove tracked packages,
rewrite upstream locations, or change maintainer-declared automation policy.
If Build is ever permitted to propose or perform such changes, that behavior must
be explicitly designed and governed rather than implied by reconciliation.

## Desired and observed state authority

Build reconciles desired state against observed and historical state, but those
categories have different authorities:

```text
Package Manifest
    maintainer-declared upstream tracking configuration

Recipe Manifest
    machine-maintained effective-recipe and revision history

Package History
    machine-maintained upstream observations and version-assessment decisions

Other runtime state
    machine-maintained build, validation, publication, and escalation state

Package Database
    published architecture-scoped distro package catalog
```

Observed or historical state may inform reconciliation, revision allocation,
validation, publication, and escalation. It must not by itself change the
upstream tracking configuration expressed by the Package Manifest.

Successful publication updates the Package Database rather than turning Build
history itself into the package catalog consumed by Manage.

## Recipe Manifest

The Recipe Manifest is machine-maintained state used by Build to track recipe
definitions and their relationship to package versions and revisions.

It must preserve enough history for Build to determine whether a current recipe
definition corresponds to an already-known package revision or requires a new
revision.

Conceptually:

```text
name + version + architecture
    |
    +---- r1 -> recipe_id A
    +---- r2 -> recipe_id B
    +---- r3 -> recipe_id C
```

The Recipe Manifest therefore provides the authoritative revision-to-recipe
mapping needed by Build's package identity rules.

The exact storage format, retention policy, and publication model are not yet
specified.

## Package History

Package History is machine-maintained Build state used to preserve upstream
observations and version-assessment decisions that are distinct from recipe
revision history.

It exists so that autonomous reconciliation does not need to rediscover or
silently reinterpret prior upstream-version decisions on every run.

Conceptually, Package History may preserve information such as:

```text
package: example

observed upstream versions:
    1.8
    1.9
    1.10
    2.0rc1

accepted package versions:
    1.8
    1.9
    1.10

version assessment:
    automatic / package-specific / manual
```

A package whose upstream version scheme cannot be interpreted safely may be
flagged for package-specific or manual determination. The resulting decision
must be preservable as Build state so later reconciliation can use the prior
decision rather than guessing again.

Package History does not define what is currently published. Publication
authority belongs to the architecture-scoped Package Database.

The exact Package History schema, retention policy, and relationship to raw
upstream observations remain undecided.

## Recipe change detection

Build must be able to detect recipe-file changes mechanically.

A stored recipe-file or recipe-definition hash may be used as the first-level
change detector:

```text
recorded hash == current hash
    -> no detected recipe-file change

recorded hash != current hash
    -> inspect and classify the change
```

A changed raw file hash does not by itself require a package revision change.

The runtime may compare the changed recipe with its previously recorded form in
order to classify whether the modification is consequential to package
definition or output.

Examples of changes that may be non-consequential include comments or explicitly
non-effective metadata.

Examples of changes that are expected to be consequential include categories
such as:

- source declarations;
- patches;
- build commands;
- configure or build options;
- declared dependencies;
- recipe-controlled build settings.

If the runtime can determine that the effective recipe changed, the package
revision must change according to the Package Model.

If the runtime can determine that only non-effective content changed, it may
update its recorded recipe-file state without allocating a new package
revision.

If the runtime cannot safely classify a recipe change, it must escalate rather
than silently treating the change as consequential or non-consequential.

The diff and classification mechanism is intentionally not specified here.

## Recipe identity and revision authority

`recipe_id` identifies the effective recipe definition and remains distinct from
the human-facing package revision.

The package revision itself must not participate in the effective-recipe
content used to derive `recipe_id`; otherwise the revision would become part of
the definition it is intended to identify.

Conceptually:

```text
effective recipe definition
          |
          v
       recipe_id
          |
          v
Recipe Manifest mapping
          |
          v
       revision
```

The exact canonical effective-recipe representation and recipe identity
algorithm remain undecided.

## Upstream reconciliation

Build is expected to monitor upstream sources for package updates according to
package-specific policy.

An upstream software update and a local recipe change are different events:

```text
upstream software changes
    -> may require a new package version

effective recipe changes for the same software version
    -> requires a new package revision
```

The runtime may eventually perform source discovery, recipe adaptation, build
execution, validation, and package publication automatically where package
policy permits.

The exact upstream discovery mechanisms, polling intervals, release-selection
rules, version-assessment algorithms, package-specific comparison mechanisms,
and automatic recipe-editing mechanisms remain undecided.

## Package-production state transitions

A successful build and a published package are different states.

Conceptually, package-production work may progress through states such as:

```text
detected
   |
   v
prepared
   |
   v
built
   |
   v
validated
   |
   v
publishable
   |
   v
published
```

These names are conceptual rather than a final persisted state machine, but the
design requires publication to remain a distinct transition from build success
and validation success.

Automation policy may permit different packages to stop at different points.
For example, an assisted package may reach a validated or publishable state and
require human approval before publication.

The exact state machine, approval semantics, and publication transaction model
remain undecided.

## Automation classes

Packages must be classifiable according to the level of automation Build is
permitted or expected to perform.

The initial semantic classes are:

### auto

The package is expected to support an automated path through upstream detection,
required package-definition updates, build, validation, and publication where
the runtime can resolve the change safely.

Human intervention is exceptional.

### assisted

Build may detect upstream or recipe changes and perform safe portions of the
update workflow, including candidate preparation, build, or validation, but
some transitions may require explicit human review or approval.

### manual

Build may monitor and report changes, but package-definition modification or
publication is not expected to proceed autonomously.

Human intervention is part of the normal update path.

These classes express policy, not implementation capability guarantees.

The exact class names and serialized values may be refined later, but the design
requires package-specific automation policy rather than universal autonomy.

## Capability detail

Automation class is a high-level policy.

Later design may additionally describe which individual stages are automated for
a package, such as:

- upstream discovery;
- source update;
- recipe update;
- build;
- validation;
- publication.

This allows a package to be highly automated without requiring every stage to
share the same automation behavior.

The capability representation is not yet specified.

## Escalation

Autonomous operation must have an explicit escalation path.

When Build encounters a condition it cannot resolve safely, it must preserve the
failure or ambiguity as actionable state and make it possible to alert a human
operator.

Examples include categories such as:

- an upstream change that cannot be interpreted;
- a recipe change that cannot be classified safely;
- an update that requires non-mechanical recipe work;
- repeated or unresolvable build failure;
- validation failure;
- publication preconditions that cannot be satisfied safely.

Escalation is a normal outcome of the reconciliation model, not an exceptional
violation of it.

The alert transport, severity model, retry policy, acknowledgement mechanism,
and operator workflow remain future design topics.

## Build-state authority

Build owns package-production state required to perform autonomous
reconciliation.

This state is distinct from Manage's authoritative installed-package state.

Build's package-production state may include the Recipe Manifest, Package
History, observed upstream state, build results, validation state, publication
state, and escalation state as later design specifies. Build consumes the
Package Manifest as maintainer-declared upstream tracking input and publishes
eligible package identities into the architecture-scoped Package Database.

Manage remains authoritative only for package state installed on a target
filesystem.

## Undecided areas

This design intentionally does not yet decide:

- Package Manifest, Recipe Manifest, and Package History file formats or schemas;
- scheduler or worker architecture;
- polling intervals;
- upstream service integrations;
- automatic recipe-editing strategy;
- recipe diff implementation;
- recipe-change classifier implementation;
- retry and backoff policy;
- alert or notification transport;
- operator approval interface;
- artifact publication mechanism;
- package repository implementation;
- dependency-driven rebuild policy;
- validation depth required before autonomous publication;
- exact package-production state machine and persisted state names;
- rules, if any, for Build proposing or mutating desired-state policy.
