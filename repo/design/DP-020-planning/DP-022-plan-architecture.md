---
doc_id: DP-022
title: Plan Architecture
depends_on:
  - DP-020
  - DP-021
---

# Plan Architecture

## Purpose

The Plan is the technical specification for implementing one Functional Set.

It translates selected Design into sufficiently concrete technical intent for Build without turning Planning into implementation.

## Content

The Plan describes the technical decisions that materially affect correct realization of the Functional Set.

Depending on the work, this may include:

- technical structure;
- interfaces;
- behavior;
- data flow;
- constraints;
- affected implementation areas;
- integration points;
- sequencing where consequential; and
- implementation invariants.

These are available forms of technical specification rather than mandatory universal sections.

## Resolution

The Plan should resolve consequential technical choices that Build should not invent.

Ordinary code-level decisions remain with Build.

The Plan should not prescribe exact functions, line-by-line changes, exhaustive pseudocode, or every file mutation unless those details are materially necessary to preserve intended architecture, behavior, or correctness.

## Relationship to Normative Requirements

The Plan and normative requirements are separate Planning outputs.

The Plan explains how the selected Design is intended to be realized technically.

Normative requirements state the precise obligations the realized work must satisfy.

Neither output replaces the other.

## Boundaries

If Planning encounters a missing semantic decision, work returns to Design.

If Build later discovers that a consequential technical decision is unresolved or defective, work returns to Planning.

Build may make local implementation choices that preserve the Plan, normative requirements, Functional Set scope, and Design meaning.

## Simplicity

The Plan should be no more detailed than necessary for Build to proceed without inventing consequential technical intent.

More detail is not automatically better. Detail that does not materially improve correctness, understanding, or necessary agent control should be omitted.
