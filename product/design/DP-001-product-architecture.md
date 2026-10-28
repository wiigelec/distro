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

Build is an autonomous system responsible for producing the files from source that make up Distro packages and orchestrating their creation and publication through Manage.

It acquires sources, compiles them, and installs build outputs into staging filesystems. Build owns creation of package file contents and coordinates package production as software changes over time; it does not assemble or publish package archives or own installed package state.

The detailed scope of autonomy, its policy boundaries, package discovery, and production workflow remain to be designed.

### Manage

Manage is responsible for creating Distro packages from Build-produced files, publishing packages to a specified repository, and managing packages on target systems, including installation, removal, upgrades, and tracking installed package state. Manage owns package assembly, package metadata, publication, and installed package state; it does not compile source or produce build output files.

The package creation and publication interfaces are defined in DP-004.

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

Build produces package file contents and invokes Manage to create and publish packages. Manage also applies package operations to target systems. Install uses Manage while creating and configuring a system.

The mechanisms for package publication, distribution, and consumption remain to be defined. This document does not establish the package repository as an additional primary component.

## Progressive Design Decomposition

This document is a high-level Design baseline, not an exhaustive product specification.

As development selects bounded Functional Sets, the relevant product concepts may be decomposed into further Design documents as needed to resolve consequential meaning and responsibility boundaries. Selecting a Functional Set does not itself create or settle missing Design intent.

Details unrelated to the selected work may remain open. Subsequent Planning is responsible for selecting scope and deriving technical obligations from sufficiently reviewed Design; it must not infer unspecified Product Design decisions from prototype implementation or historical behavior.

## Prior Prototype

The earlier `wiigelec/distro-proto` repository is reference material for possible Design elaboration. Its implementation, Planning, and historical decisions do not automatically become normative authority for this product.
