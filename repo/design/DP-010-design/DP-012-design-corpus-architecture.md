---
doc_id: DP-012
title: Design Corpus Architecture
depends_on:
  - DP-010
  - DP-011
---

# Design Corpus Architecture

## Purpose

The Design corpus is the maintained collection of Markdown Design documents that records intended system meaning.

This architecture defines the minimum identity and relationship structure needed to keep that corpus understandable and referencable.

## Canonical Documents

Markdown Design documents are the semantic source of the Design corpus.

Generated metadata, indexes, summaries, embeddings, or other machine aids may assist discovery or ingestion, but they do not replace the canonical Markdown meaning.

## Document Identity

Each Design document has one `DP-NNN` identity within a Design revision.

The identity provides a concise way to refer to the document in that revision. When the corpus is intentionally reorganized, document identities may be renumbered as part of the same coherent revision.

Historical interpretation remains bound to the exact Design revision consumed, so references remain unambiguous across renumbering.

Identity applies at the document level. The framework does not require identities on every statement, paragraph, heading, or requirement-like sentence.

## Document Relationships

A Design document may declare semantic dependencies on other Design documents that are needed to interpret its meaning.

Dependencies describe interpretation relationships.

They do not define lifecycle order, implementation order, acceptance order, or authority precedence beyond the semantic relationship expressed by the Design itself.

Parent-child decomposition and semantic dependency are separate ideas.

A child may depend on its parent, and a document may also depend on related documents elsewhere in the corpus.

## Corpus Evolution

The Design corpus may evolve as understanding grows.

Documents may be added, corrected, decomposed, consolidated, or retired when doing so better represents intended system meaning.

Existing Planning work remains bound to the exact Design revision it consumed rather than silently inheriting later Design changes.

## Partial Design

The Design corpus does not need to be globally complete before useful Planning can occur.

A sufficiently developed portion of the corpus may support a bounded Functional Set while unrelated Design remains incomplete.

The relevant Design Review determines whether the Design needed for the intended Planning work is sufficiently complete.

## Reference Precision

References to Design should use the lightest mechanism that still identifies the intended meaning reliably.

Document identity, headings, direct links, or other human-readable references may be sufficient.

The framework should not introduce statement-level identity or generalized provenance merely because more granular reference is theoretically possible.

## Repository Layout

This architecture does not require a specific directory depth, file naming convention beyond stable Design identity, or generated index structure.

Concrete repository organization should be chosen during Planning when implementation of the Design system requires it.

## Simplicity

The Design corpus should remain understandable by opening and reading its Markdown documents.

Supporting machinery is justified only when it materially improves discovery, interpretation, traceability, or necessary agent control without replacing the documents themselves as the source of meaning.
