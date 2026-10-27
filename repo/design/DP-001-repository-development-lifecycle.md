---
doc_id: DP-001
title: Repository Development Lifecycle
depends_on: []
---

# Repository Development Lifecycle

## Purpose

This repository framework exists to turn conversational human intent into correct working software while keeping the process understandable, bounded, and simple.

The framework has six major concerns: Design, Planning, Build, Validation, Semantic Review, and Acceptance.

Their lifecycle relationship is:

    Design
      ↓
    Design Review
      ↓
    Planning
      ↓
    Planning Review
      ↓
    Build
      ↓
    Validation
      ↓
    Build Review
      ↓
    Acceptance

Each concern exists only to support development of the actual project.

Every lifecycle artifact, process, and mechanism should be kept as simple as practicable while still preserving the user's intent, required behavior, correctness, necessary constraints, and necessary control of the AI agent.

A downstream artifact or process may realize, validate, or review upstream intent, but it does not create new persistent intent merely by existing. Implementation behavior, validation behavior, review findings, generated artifacts, and historical repository behavior do not independently become Design or normative requirements.

When controlling upstream Design or Planning state is materially missing, ambiguous, or contradictory for a consequential downstream decision, downstream work shall not resolve the defect by invention. Work returns to the stage that owns the defective decision before dependent realization proceeds.

Lifecycle stages describe development intent, decisions, responsibilities, and control flow. They do not define the storage hierarchy of implemented repository state.

Durable implementation artifacts such as source, configuration, tests, validation definitions, manifests, and generated project artifacts exist as repository state outside the lifecycle document hierarchy. A lifecycle stage may create, modify, consume, validate, or review such an artifact without making that artifact a child of the stage.

## Design

Design is the bridge between human and machine understanding.

Design captures intended system meaning as human-readable Markdown organized for reliable machine ingestion. It is developed as a hierarchical outline whose concepts are decomposed naturally as more detail is required.

Design owns system meaning.

See DP-010.

## Planning

Planning is the technical bridge between Design and Build.

Planning consumes Design and existing repository state, selects a bounded Functional Set, and develops the technical specification and normative requirements needed to implement that work. Planning also classifies each normative requirement for mechanical evaluation, semantic evaluation, or both.

Planning owns Functional Set scope, technical specification, and normative distillation while leaving ordinary code-level implementation decisions to Build.

See DP-020.

## Build

Build is the physical manifestation of Design and Planning.

Build transforms the reviewed Planning result into actual repository state while preserving intended meaning, technical constraints, normative obligations, and Functional Set scope.

Build owns implementation correctness, ordinary code-level decisions, implementation of mechanical validation tasks, and the exact binding from mechanical normative requirements to those tasks.

See DP-030.

## Validation

Validation mechanically enforces mechanically decidable normative requirements and helps bound the AI agent.

Mechanical enforcement must be directly traceable to the normative requirement it enforces. Validation does not invent normative intent.

Validation is a gate to acceptance, not a separately documented lifecycle result.

See DP-040.

## Semantic Review

Semantic Review evaluates alignment and semantic sufficiency at designated review points after Design, Planning, and Build and is normally iterative.

Design Review evaluates Design for semantic completeness.

Planning Review evaluates the complete Planning result against Design.

Build Review evaluates Build against both Planning and Design.

Semantic Review also challenges unnecessary complexity and asks whether a materially simpler solution could preserve the same intent, required behavior, correctness, necessary constraints, and necessary agent control.

Review findings are working-process information and do not require durable governance records.

See DP-050.

## Acceptance

Development work occurs on a development branch.

The development branch contains candidate work. `main` contains accepted repository state.

Applicable Validation and Semantic Review must be satisfactory before integration. If they are not satisfactory, the candidate remains on the development branch and is corrected there.

For this single-developer repository, intentionally merging the development branch into `main` is acceptance. No parallel acceptance record, receipt, provider reconstruction, or separate acceptance history is required.

See DP-060.
