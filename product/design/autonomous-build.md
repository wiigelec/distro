# Autonomous Build Runtime

## Purpose

Build is not limited to executing a single package recipe on demand.

The distro design expects Build to evolve into an autonomous package-production
runtime that maintains the distro's declared package set by reconciling package
policy, recipe state, upstream state, and produced package artifacts.

This document defines that architectural direction without choosing the runtime
implementation, scheduler, polling mechanism, manifest serialization, or alert
transport.

## Reconciliation model

At the architectural level, Build operates as a reconciler:

```text
desired package set
      |
      v
Package Manifest
      |
      v
 Build Runtime <--------- upstream state
      |
      +----> recipe state
      |
      +----> build scheduling
      |
      +----> package production
      |
      +----> validation
      |
      +----> publication state
      |
      +----> escalation when automation cannot proceed safely
```

The runtime compares desired and observed state and performs package-production
work required to bring the distro package set toward the declared desired state.

Autonomy is policy-driven and package-specific. The design does not assume that
every package can be updated with the same level of automation.

## Package Manifest

The Package Manifest is the authoritative declaration of packages that belong to
the distro package set.

At the semantic level, it must be able to associate a package with the policy
needed by Build to maintain it.

The exact fields and serialization remain undecided, but the manifest is
expected eventually to represent categories such as:

- package name or package-set identity;
- recipe reference;
- supported architecture scope;
- upstream discovery policy;
- package automation policy;
- package state required for autonomous reconciliation.

The Package Manifest describes desired package membership and policy. It is not
the installed-package database owned by Manage.

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
rules, and automatic recipe-editing mechanisms remain undecided.

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

Build's package-production state may include the Package Manifest, Recipe
Manifest, observed upstream state, build results, and publication state as later
design specifies.

Manage remains authoritative only for package state installed on a target
filesystem.

## Undecided areas

This design intentionally does not yet decide:

- manifest file formats or schemas;
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
- validation depth required before autonomous publication.
