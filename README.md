# Repository

This repository uses an installed repo-spec lifecycle framework.

## Lifecycle

Work proceeds through Design, Planning, Build, Validation, Semantic Review, and Acceptance.

`main` represents accepted repository state.

## Repository surfaces

- `repo/design/` — installed framework Design.
- `repo/specs/` — installed framework normative specifications.
- `repo/scripts/validate` — framework-owned mechanical Validation entry point.
- `scripts/validate` — repository-wide mechanical Validation entry point.
- `product/` is the product-owned domain. Product meaning is established independently through Product Design.
- `product/design/` — starting surface for Product Design.
- `user/` — user-owned operational material outside the framework.

Begin substantive product work in Product Design.

The exact repo-spec framework source revision used to initialize this repository is recorded in `repo/validation/framework-source.json`.

Validation is mechanical evaluation only. Semantic Review evaluates meaning and fidelity. Acceptance is intentional integration of a satisfactory candidate into `main`.
