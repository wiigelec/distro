# Repository Agent Guidance

This file provides operational guidance and does not independently define normative meaning.

## Lifecycle ownership

A missing consequential semantic decision → **Design**.

A Functional Set, Plan, normative requirement, scope, or evaluation-classification defect → **Planning**.

An implementation or mechanical-enforcement-construction defect → **Build**.

Validation does not create Design meaning or normative requirements.

## Repository ownership

`repo/` is the reusable repository-development framework.

`product/` is the generic product-owned domain. Do not assume Product meaning before Product Design establishes it.

`scripts/` is the narrow repository-wide operational composition role.

`user/` is user-owned operational material outside the framework.

Closed architectural boundaries are default-deny. Do not add new direct children or files where the accepted architecture does not allow them.

## Build discipline

Consume reviewed Design and Planning. Prefer the simplest implementation that preserves their meaning and satisfies applicable normative requirements.

Do not infer normative intent from implementation behavior.

## Validation

Use `scripts/validate` as the repository-wide mechanical Validation entry point. `repo/scripts/validate` remains authoritative for framework mechanical checks.

Mechanical Validation passing does not establish semantic acceptance.

## Semantic Review and Acceptance

Semantic Review evaluates the realized candidate against the complete applicable Design and Planning result.

`main` represents accepted state. Acceptance occurs only through intentional integration of a satisfactory candidate into `main`.
