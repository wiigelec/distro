---
doc_id: DP-040
title: Validation Architecture
depends_on:
  - DP-001
  - DP-020
  - DP-030
---

# Validation Architecture

## Purpose

Validation mechanically evaluates the mechanically decidable portions of normative requirements and helps bound the AI agent.

Validation does not define normative intent. Its enforcement basis comes from Planning, while Build constructs the executable checks and their requirement bindings.

## Architecture

Planning owns each normative requirement's active/inactive state and classifies each requirement as mechanical, semantic, or both. Classification is retained while inactive, but inactive requirements carry no current Validation or Semantic Review obligation.

Build constructs the concrete mechanical enforcement and records exact requirement-to-task bindings in the durable Requirement Evaluation Manifest.

The manifest is repository state outside the lifecycle document hierarchy. It exists to make concrete mechanical enforcement traceable, not to contain or own Planning intent.

Validation consumes the manifest and the referenced enforcement tasks, executes the applicable checks against candidate repository state, and interprets their mechanical pass or fail result.

Only reliably mechanically decidable obligations belong in mechanical Validation.

## Execution

Validation runs each required mechanical enforcement task justified by active normative requirements and applicable to the candidate.

It may use ordinary test runners, scripts, linters, build commands, repository checks, or other project-native mechanisms. A universal validation runner is not required when existing tooling can execute the required checks reliably.

## Failure Routing

A failing validation task means the candidate does not currently satisfy at least one mechanically enforced obligation.

The defect is corrected in the stage that owns it: Design for semantic meaning, Planning for technical specification or normative distillation, and Build for implementation or enforcement construction.

Validation does not silently modify upstream lifecycle decisions in response to failure.

## Result Meaning

A passing mechanical task establishes only that its mechanically decidable condition passed for the candidate state checked.

Mechanical success does not prove semantic completeness, faithful interpretation, or acceptance. Semantic questions remain with Semantic Review, and acceptance remains governed by DP-060.

## Boundaries

Validation is proportional to the behavior and risk it protects.

Project-native test and validation mechanisms should be reused when they can enforce the required obligation reliably.

Semantic completeness, faithful interpretation, unnecessary complexity, scope meaning, and other non-mechanical judgments remain with Semantic Review.

Passing Validation is a gate condition, not acceptance and not a separate durable lifecycle result.

All required mechanical validation applicable to the candidate must pass before the candidate is eligible for acceptance. Optional diagnostic, exploratory, performance, development, or informational checks do not become acceptance gates unless Planning establishes a normative obligation that makes them required.

## Repository-Wide Validation Composition

A repository may provide one repository-root Validation entry point that composes the canonical Validation entry points of the ownership domains present in that repository.

Repository-wide composition coordinates execution only. Framework Validation remains owned by `repo/`; product Validation remains owned by `product/`. The root composition layer does not duplicate, reinterpret, or create normative predicates.

The repository-root Validation entry point shall run required framework Validation and shall also run product Validation when the product ownership domain provides its canonical Validation entry point. Failure in any required participating domain makes repository-wide Validation fail.

CI should delegate its mechanical gate to the repository-root Validation entry point when that composition surface exists, rather than independently selecting domain validators or reproducing their checks.

## Product Validation Contract

A repository prepared for product lifecycle work has a canonical product Validation entry point and a product-owned Validation implementation domain as defined by the repository ownership architecture.

The product entry point delegates execution into product-owned Validation implementation. Substantive product mechanical predicates, requirement-task dispatch, and product validation fixtures remain under the product Validation ownership surface rather than accumulating in the entry point or repository-root composition layer.

The product Requirement Evaluation Manifest is the durable traceability boundary between mechanically evaluated product normative requirements and their product validation tasks. Product Validation consumes those bindings to determine the mechanically required product checks.

Framework Validation shall evaluate the reliably mechanically decidable generic properties of that contract, including required product Validation surfaces, manifest structural validity, mechanically classified requirement coverage, and whether referenced task identities resolve within the product Validation mechanism. Framework Validation does not thereby execute or own the product-specific normative predicate represented by a task; the canonical product Validation entry point remains responsible for product mechanical evaluation.

A product with no applicable mechanically evaluated normative requirements still retains the canonical product Validation substrate. Its empty valid manifest represents the absence of current product mechanical obligations rather than the absence of product Validation architecture.


For an installed framework snapshot identified by its framework source record, framework Validation may omit checks whose subject is framework-development Planning history that is intentionally absent from that snapshot. Remaining installed framework normative state remains mechanically evaluated from the installed normative specifications, requirement-evaluation bindings, and applicable framework artifacts.
