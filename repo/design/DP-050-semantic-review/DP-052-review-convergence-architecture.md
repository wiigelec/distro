---
doc_id: DP-052
title: Review Convergence Architecture
depends_on:
  - DP-050
  - DP-051
---

# Review Convergence Architecture

## Purpose

Review convergence defines how Semantic Review iterates until material semantic discrepancies are resolved.

Semantic Review is expected to require multiple passes when a candidate contains meaningful defects.

## Iteration

A review pass examines the current candidate, identifies material discrepancies, and routes each discrepancy to the stage that owns the defective decision.

The owning stage corrects the candidate.

Semantic Review then evaluates the corrected result again.

The cycle continues while unresolved material semantic discrepancies remain.

## Convergence

Review converges when no unresolved material semantic discrepancy remains for the stage being reviewed.

Convergence does not mean that every possible improvement has been made.

Minor preferences, speculative future improvements, and complexity with no material effect on intent, behavior, correctness, necessary constraints, or necessary agent control do not need to prevent convergence.

## Challenge

Semantic Review should attempt to falsify the preferred solution rather than merely confirm that its pieces agree with each other.

Review should ask whether:

- assumptions were invented;
- meaningful alternatives were ignored;
- the solution solves the user's actual problem;
- complexity accumulated without necessary capability;
- a simpler mechanism could preserve the same required result; or
- a newly introduced mechanism mainly exists to support complexity introduced earlier.

Agreement between user and agent is not evidence that a design or implementation is correct.

Internal consistency is necessary but not sufficient.

## Correction Routing

A discrepancy is corrected where the defective decision originated.

Downstream stages should not conceal an upstream defect by inventing missing intent, changing scope, or redefining an obligation locally.


## Working Notes

Review findings may be kept temporarily when useful for an active iteration.

The lifecycle does not require those notes to become durable governance records once review has converged.

Durable review records are not required for convergence.

## Gate Effect

If required Semantic Review has not converged, the candidate is not eligible for acceptance.

Convergence is therefore a lifecycle condition, not a separate acceptance artifact.

## Simplicity

The convergence loop should remain:

    review
      ↓
    identify material discrepancy
      ↓
    correct owning stage
      ↓
    review again

Additional review machinery is justified only when a concrete problem cannot be solved by this direct loop.
