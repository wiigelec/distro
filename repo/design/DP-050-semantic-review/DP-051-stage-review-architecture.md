---
doc_id: DP-051
title: Stage Review Architecture
depends_on:
  - DP-050
  - DP-010
  - DP-020
  - DP-030
---

# Stage Review Architecture

## Purpose

Stage Review defines the semantic questions asked after Design, Planning, and Build.

Each review evaluates the stage according to the decisions that stage owns while preserving traceability to upstream intent.

## Design Review

Design Review evaluates whether Design is sufficiently complete and coherent for downstream Planning.

It checks for:

- missing meaning or behavior;
- ambiguity or contradiction;
- unresolved consequential decisions;
- invented assumptions;
- unnecessary complexity;
- ignored meaningful alternatives; and
- failure to faithfully capture human intent.

Design Review does not require Design to be globally complete before any Planning can begin. It evaluates whether the Design needed for the intended downstream work is semantically sufficient.

## Planning Review

Planning Review evaluates the complete Planning result against the selected Design.

It checks whether:

- the Functional Set is appropriately bounded;
- the Plan faithfully and sufficiently translates Design into technical intent;
- normative requirements accurately distill the obligations needed to realize Design;
- evaluation classification is appropriate;
- mechanically classified obligations are actually mechanically decidable;
- semantic obligations have not been forced into artificial predicates; and
- Planning has not invented missing Design meaning.

Planning Review evaluates Planning as a whole rather than reviewing only the Plan.

## Build Review

Build Review evaluates realized repository state against both Planning and Design.

It checks whether:

- implementation faithfully realizes the Plan;
- normative requirements are satisfied semantically where applicable;
- underlying Design meaning is preserved;
- Functional Set scope has not drifted;
- unintended additions or omissions were introduced;
- consequential architecture changed accidentally; and
- required mechanical requirement-to-task bindings were completed.

Following the Plan mechanically is not sufficient when the Plan itself failed to preserve Design meaning.

## Semantic Normative Requirements

A normative requirement classified for semantic evaluation is evaluated during the review of the stage where its subject can meaningfully be judged.

Semantic evaluation determines whether the reviewed subject satisfies the meaning of the requirement.

A requirement classified for both semantic and mechanical evaluation may rely on mechanical Validation for its mechanically decidable portion without treating that result as proof of semantic completeness.

## Review Boundaries

Review identifies defects but does not change ownership of the decisions being reviewed.

A semantic defect returns to Design.

A Functional Set, Plan, normative-requirement, or evaluation-classification defect returns to Planning.

An implementation or mechanical-enforcement-construction defect returns to Build.

Review does not create new persistent Design meaning or normative obligations merely by identifying a discrepancy.

## Simplicity

Stage Review is a reasoning activity, not a review artifact hierarchy.

Stage Review should remain direct reasoning over the reviewed subject and its governing upstream intent.
