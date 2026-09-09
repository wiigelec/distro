---
doc_id: DP-021
title: Functional Set Architecture
depends_on:
  - DP-020
---

# Functional Set Architecture

## Purpose

A Functional Set is the bounded unit of work selected during Planning.

It groups the Planning outputs needed to realize one coherent and manageable end-to-end change without requiring the entire Design corpus to be implemented at once.

## Selection

Planning selects a Functional Set by comparing available Design with existing repository state and identifying a useful bounded change.

The boundary should be large enough to produce meaningful working behavior and small enough to remain understandable, implementable, reviewable, and correctable.

A Functional Set is selected from Design. It does not create or own Design meaning.

## Design Binding

Each Functional Set must identify the exact Design state consumed by Planning.

A repository Git revision may identify the consumed Design corpus when one revision is sufficient to reproduce that state.

The Functional Set must also identify the portion of Design selected for the work with enough precision to understand the intended scope.

Design selection should remain lightweight. It should not require statement identities on every Design sentence merely to establish traceability.

## Planning Context

A Functional Set groups:

- the selected Design scope;
- the Plan;
- normative requirements;
- current normative requirement active/inactive state; and
- normative requirement evaluation classification.

Planning may later inactivate or reactivate a normative requirement without changing its identity or normative text. Build later creates the exact mechanical requirement-to-validation-task bindings needed to realize the currently active obligations of the Functional Set. Those bindings are repository state, not part of the Planning output.

## Boundaries

A Functional Set does not need to describe every future implementation step or establish a complete implementation graph for the Design corpus.

Its boundary and relationship to Design should be represented directly, without additional lifecycle structure unless a concrete repository need requires it.

The Functional Set boundary should change only through Planning. If implementation reveals that the selected work cannot remain coherent within its current boundary, work returns to Planning.

## Simplicity

The Functional Set should contain only the information needed to identify the bounded work and relate its Planning outputs.

Its representation should remain as simple as practicable while preserving scope, Design traceability, correctness, and necessary agent control.

## Portable Design Binding

A Functional Set's Design binding identifies the exact Design state Planning consumed. When a Git revision is used for that binding, the revision value remains the identifier of that consumed state even if the Functional Set is later carried into an independently rooted repository that does not contain the originating Git object.

The binding shall be preserved accurately. Mechanical Validation may enforce the required representation and any explicitly fixed value, but portability shall not be defeated merely by requiring an originating commit object to exist in the current repository.

An operation may use stronger local-history checks when controlling Design or Planning explicitly requires local-history membership for that operation. Such a rule does not redefine the portable meaning of the retained Design binding.
