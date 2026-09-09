# Product Design

This directory contains the human-readable Product Design for the distro.

The initial architecture is intentionally small and defines three primary
components:

- [Build](build.md) — turns source plus a package recipe into package artifacts.
- [Manage](manage.md) — owns installed package state and package transactions.
- [Install](install.md) — creates a configured system by orchestrating package
  installation and system setup.

See [Architecture](architecture.md) for the component boundaries and
[Interfaces](interfaces.md) for the contracts between them.

These documents establish the initial design baseline. Details not explicitly
decided here remain open design questions and should be resolved by later
Product Design changes.
