---
doc_id: DP-020
title: Planning Architecture
depends_on:
  - DP-001
  - DP-010
---

# Planning Architecture

## Purpose

Planning is the technical bridge between Design and Build.

Planning consumes Design and existing repository state, selects bounded work, and produces the technical information Build needs without forcing Build to invent consequential semantic or architectural decisions.

## Architecture

The bounded unit of work is the Functional Set.

For each Functional Set, Planning produces:

- selected Design scope bound to the exact Design state consumed;
- a Plan describing consequential technical intent;
- normative requirements stating precise obligations;
- current normative requirement state, active or inactive; and
- evaluation classification identifying each requirement as mechanical, semantic, or both.

Planning does not need to identify exact mechanical validation tasks before Build constructs them.

Traceability should remain direct and lightweight: enough to identify the consumed Design meaning and the obligations derived from it without forcing statement-level identity onto Design.

## Further Design

Planning is decomposed into:

- DP-021 — Functional Set Architecture
- DP-022 — Plan Architecture
- DP-023 — Normative Requirements Architecture

These children own the detailed semantics of Planning outputs.

## Boundaries

Planning owns Functional Set scope, technical specification, normative requirement creation, normative requirement active/inactive state, and evaluation classification.

Missing product or system meaning returns to Design.

Ordinary implementation decisions remain with Build.

Downstream implementation, validation, review findings, generated artifacts, or historical behavior do not independently create or amend normative requirements.

## Review

Planning Review evaluates the complete Planning result against selected Design.

It checks scope, technical fidelity, normative completeness, requirement state, evaluation classification, and whether mechanical evaluation is limited to active reliably decidable obligations.
