---
doc_id: DP-011
title: Semantic Decomposition Architecture
depends_on:
  - DP-010
---

# Semantic Decomposition Architecture

## Purpose

Semantic decomposition defines how Design moves from broad human intent to sufficiently detailed technical understanding.

Design is organized as an outline in which broad concepts are progressively decomposed into smaller logical concepts.

## Decomposition Model

A Design concept begins at the highest useful level of abstraction.

When that concept contains multiple independently meaningful concerns, it is decomposed into child concepts.

Each child may then be decomposed again.

This continues until the concept is sufficiently narrow and detailed for downstream Planning to understand the intended system without requiring Design to prescribe implementation.

## Partitioning Principle

Decomposition follows meaning.

A new child Design document is justified when separating a concept materially improves understanding, navigation, independent reasoning, or downstream consumption.

Document size, token count, line count, or a fixed number of sections do not independently justify decomposition.

A concept should remain in its parent when splitting it would create fragments that are harder to understand than the combined idea.

## Parent and Child Roles

A parent Design document describes a concept at one level of abstraction.

A child Design document expands one logical partition of that parent in greater detail.

The child should preserve the parent's meaning while adding necessary detail.

A child does not acquire independent authority to contradict or silently redefine the parent.

If deeper understanding reveals that the parent meaning is wrong, the parent Design should be corrected.

## Cross-Cutting Concepts

Not every semantic relationship is hierarchical.

Related concepts may use cross-references or semantic dependencies when one is needed to interpret another but neither is naturally a child of the other.

The framework should not force every relationship into a tree merely to preserve a visual hierarchy.

## Stopping Condition

Decomposition stops when the current Design partition is sufficiently clear and detailed for its purpose.

For Design that will be consumed by Planning, sufficient detail means Planning can identify the intended meaning, relevant boundaries, and consequential semantic decisions without inventing missing product or architectural intent.

Further decomposition is not useful when it merely converts readable Design into finer administrative fragments.

## Content Shape

Design remains prose-oriented.

Headings, lists, examples, diagrams, and other Markdown structure may be used when they improve understanding.

The framework does not require a universal section template for every Design document.

The structure of each document should follow the semantics of the concept being explained.

## Simplicity

Semantic decomposition should create the minimum number of Design partitions needed to make intent understandable and usable.

More documents are not evidence of better Design.
