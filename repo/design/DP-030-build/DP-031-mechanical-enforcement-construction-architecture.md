---
doc_id: DP-031
title: Mechanical Enforcement Construction Architecture
depends_on:
  - DP-030
  - DP-023
  - DP-040
---

# Mechanical Enforcement Construction Architecture

## Purpose

Mechanical enforcement construction is the part of Build that creates the executable Validation tasks required by active mechanically classified normative requirements.

Build constructs the enforcement. Validation executes it.

## Normative Basis

Planning determines which active normative requirements require mechanical evaluation. Inactive requirements require no current enforcement.

Build does not decide that a new obligation should exist merely because a test or validator would be useful.

Every mechanical enforcement task must be justified by at least one active normative requirement requiring mechanical evaluation.

Supporting helpers, fixtures, parsers, loaders, or shared utilities do not require independent requirement mappings unless they themselves perform normative enforcement.

## Construction

Build implements the smallest reliable mechanical check that can determine the mechanically decidable obligation.

A task may enforce one or multiple normative requirements when that relationship remains understandable.

A normative requirement may map to multiple tasks when multiple checks are genuinely needed.

The architecture does not require a one-requirement-one-test structure.

## Requirement Binding

Build records the exact relationship between mechanically evaluated normative requirements and the Validation tasks that enforce them.

The binding should be direct enough to answer both directions:

- which Validation task enforces this requirement?; and
- which normative requirement justifies this Validation task?

Build records this direct mapping in the durable Requirement Evaluation Manifest.

The manifest is repository state outside the Build hierarchy. Build is responsible for creating and maintaining the mechanical bindings it contributes, but the artifact itself is not a child or owned storage location of Build.

The direct requirement-to-task mapping is sufficient unless a concrete enforcement need requires additional structure.

## Semantic Requirements

Build does not construct artificial executable checks for obligations that Planning classified as semantic.

A requirement classified for both mechanical and semantic evaluation receives mechanical enforcement only for the portion that can be decided reliably.

Semantic satisfaction remains the responsibility of Semantic Review.

## Organization

Mechanical enforcement should remain understandable when inspected locally.

A reader should be able to understand why an enforcement task exists and what behavior it protects without reconstructing a large validation framework.

Validation code should be organized around the behavior being protected rather than around framework metadata categories.

## Boundary with Validation

Build owns creation and maintenance of mechanical enforcement tasks and their requirement bindings.

Validation owns execution of those tasks against candidate Build state and interpretation of their mechanical pass or fail result.

Passing a task does not create acceptance, semantic proof, or a durable lifecycle record.

## Simplicity

Mechanical enforcement construction should remain proportional to the behavior and risk being protected.

The framework should prefer direct tests and mappings over additional abstraction unless abstraction materially improves enforcement, reuse, reliability, understandability, or necessary agent control.
