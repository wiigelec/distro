---
doc_id: DP-030
title: Build Architecture
depends_on:
  - DP-001
  - DP-010
  - DP-020
---

# Build Architecture

## Purpose

Build is the physical realization of reviewed Design and Planning.

It transforms one Functional Set into repository state while preserving Design meaning, Planning intent, normative obligations, and Functional Set scope.

## Architecture

Build has two distinct responsibilities:

- realize the implementation; and
- construct and bind mechanical enforcement required by Planning's evaluation classification.

Build owns implementation correctness and ordinary code-level decisions.

Design remains the semantic source; the Plan is the immediate technical specification.

## Implementation

Build may create, modify, delete, refactor, integrate, or regenerate repository content as needed to realize the Functional Set.

Ordinary implementation choices belong to Build when they preserve Design meaning, Plan intent, normative requirements, and Functional Set scope.

Implementation correctness includes repository state that is internally coherent, technically functional, and faithful to Planning and Design. Local refactoring or integration work does not need to be enumerated by the Plan when it is an ordinary implementation consequence rather than a new technical or semantic decision.

Build should prefer the simplest implementation that faithfully realizes the reviewed Planning result and Design intent.

## Further Design

Build has one child Design:

- DP-031 — Mechanical Enforcement Construction Architecture

DP-031 defines construction of mechanical enforcement tasks and their exact requirement bindings. Validation owns execution of those tasks.

## Boundaries

Build does not invent missing Design meaning, consequential Planning decisions, new normative obligations, or broader Functional Set scope.

When implementation exposes an upstream defect, the work returns to the stage that owns the defective decision.

## Review

Build Review evaluates realized repository state against both Planning and Design.

It checks implementation fidelity, semantic preservation, scope, unintended additions or omissions, architectural drift, semantic normative requirements applicable to realized Build state, and completion of required mechanical bindings.
