---
doc_id: DP-023
title: Normative Requirements Architecture
depends_on:
  - DP-020
  - DP-021
---

# Normative Requirements Architecture

## Purpose

Normative requirements are the precise obligations developed during Planning for one Functional Set.

They provide stable statements that Build, Validation, and Semantic Review can evaluate without forcing normative syntax into human-oriented Design.

## Derivation

Normative requirements are derived from selected Design and Planning's technical interpretation of that Design.

Their relationship to Design is not required to be one-to-one.

One Design concept may produce zero, one, or multiple normative requirements, and one normative requirement may combine meaning from multiple Design concepts.

Requirement identities are assigned during Planning.

Once created, a normative requirement's identity and normative text are stable. Planning does not change the meaning of an existing requirement in place. If the obligation itself changes, Planning creates a new normative requirement and may inactivate the earlier requirement.

## Content

A normative requirement should state one coherent obligation precisely enough to determine whether the realized work satisfies it.

A requirement should preserve the intended meaning of its Design source without adding new product or architectural semantics.

A requirement may express behavior, structure, constraints, invariants, compatibility, or other obligations that must hold for the Functional Set.

## Semantic Ownership

Each normative obligation should have one controlling requirement owner. A requirement may reference, apply, or specialize an obligation controlled elsewhere, but it should not create a second independent restatement of equivalent semantics when reference to the controlling requirement is sufficient.

When a genuinely distinct obligation is required, Planning assigns it its own identity and states the distinction precisely enough that downstream Build and Review do not have to infer which requirement controls the shared meaning.

## Requirement State

Every normative requirement has a current Planning-owned state.

A requirement is active by default. Planning may mark it inactive and may later reactivate it.

Inactive state is represented separately from evaluation classification. An inactive requirement remains defined but carries no current implementation, mechanical-evaluation, or semantic-evaluation obligation.

Changing active/inactive state does not change the requirement's identity or normative text.

## Evaluation Classification

Every normative requirement has one current Planning evaluation classification:

- mechanical evaluation;
- semantic evaluation; or
- both mechanical and semantic evaluation.

Evaluation classification is independent of requirement state. For an active requirement, the classification determines how the current obligation is judged. For an inactive requirement, the classification is retained but creates no current mechanical-evaluation or semantic-evaluation obligation.

Evaluation classification does not represent requirement lifecycle state and does not require Planning to design the exact implementation of a mechanical validator.

## Boundaries

Normative requirements do not live inside the Plan and do not acquire authority from Build, Validation, review findings, historical behavior, or generated artifacts.

If a requirement cannot be written without inventing missing semantic meaning, work returns to Design.

If a requirement exposes a defective technical interpretation while Design remains sound, work remains in Planning.

## Simplicity

Requirements should be as precise as necessary and no more fragmented than useful.

They should not be split merely to satisfy an identity scheme, validation framework, or one-requirement-one-test assumption.
