---
doc_id: DP-001
title: Distro Product Architecture
depends_on: []
---

# Distro Product Architecture

## Purpose

Distro is a source-built Linux distribution. It provides the capabilities to produce and maintain its package collection, manage packages on target systems, and create usable installed systems.

This document establishes the initial product-level architecture. It intentionally leaves component internals, detailed interfaces, data formats, implementation choices, and development sequencing open for subsequent Design decomposition.

## Primary Components

Distro has three primary components: **Build**, **Manage**, and **Install**.

### Build

Build is an autonomous system responsible for creating and updating Distro's package collection.

It produces packages from source and maintains the distribution's package collection as software changes over time. Build owns package-production activity; it does not own the installed package state of individual systems.

The detailed scope of autonomy, its policy boundaries, package discovery, production workflow, and publication mechanisms remain to be designed.

### Manage

Manage is responsible for managing packages on a target system, including installation, removal, upgrades, and tracking installed package state.

Manage owns installed package state. It does not own package production.

### Install

Install is responsible for creating and configuring usable Distro systems.

Install uses Manage for package installation rather than implementing a separate package-management mechanism. Install owns the surrounding system-installation and machine-configuration process.

## Project Source and Entry-Point Layout

Each primary component has a dedicated source directory and a corresponding calling script:

```text
product/
├── src/
│   ├── build/
│   ├── manage/
│   └── install/
└── scripts/
    ├── build
    ├── manage
    └── install
```

Component implementations reside in their respective `product/src/` directories. The corresponding `product/scripts/` files are the component entry points. This layout does not prescribe implementation languages, internal module organization, or command parameters.

## Bootstrap

Bootstrap is a **one-time initialization process**, not a fourth primary component.

Its responsibility is to establish the initial Distro-native environment needed to begin operating the distribution's native capabilities. The specific starting environment, construction steps, and transition criteria remain open Design questions.

Once Distro's native capabilities are established, ongoing package production and maintenance are responsibilities of the primary components rather than Bootstrap.

## Component Relationships

Build creates and maintains packages for consumption by Manage. Manage applies package operations to target systems. Install uses Manage while creating and configuring a system.

The mechanisms for package publication, distribution, and consumption remain to be defined. This document does not establish the package repository as an additional primary component.

## Progressive Design Decomposition

This document is a high-level Design baseline, not an exhaustive product specification.

As development selects bounded Functional Sets, the relevant product concepts may be decomposed into further Design documents as needed to resolve consequential meaning and responsibility boundaries. Selecting a Functional Set does not itself create or settle missing Design intent.

Details unrelated to the selected work may remain open. Subsequent Planning is responsible for selecting scope and deriving technical obligations from sufficiently reviewed Design; it must not infer unspecified Product Design decisions from prototype implementation or historical behavior.

## Prior Prototype

The earlier `wiigelec/distro-proto` repository is reference material for possible Design elaboration. Its implementation, Planning, and historical decisions do not automatically become normative authority for this product.
