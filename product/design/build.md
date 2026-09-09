# Build

## Role

Build is the distro's package builder.

Its input is source material plus a package recipe or equivalent build
description. Its output is one or more package artifacts conforming to the
package contract consumed by Manage.

## Responsibilities

Build is responsible for the package-creation lifecycle, including the
following categories of behavior as they are designed:

- acquiring or locating source inputs;
- validating source inputs;
- preparing a build environment;
- executing package-specific build instructions;
- staging installable filesystem content;
- producing package metadata needed by Manage;
- producing package artifacts;
- reporting build success or failure.

## Boundary with Manage

Build creates packages; it does not install them into the authoritative package
state of the host or target system.

A package emitted by Build must be consumable by Manage without requiring
Manage to reproduce the build.

Build may require packages or other tools in order to perform a build, but that
does not make build dependency handling part of Manage's package-creation
responsibility.

## Boundary with Install

Install does not need Build in order to install a system from already-created
packages.

Build does not own disk preparation, target-system configuration, bootloader
installation, or installation workflow.

## Initial interface concept

At the architectural level:

```text
source inputs + package recipe
              |
              v
            Build
              |
              v
       package artifact(s)
```

The exact command-line interface, recipe schema, build environment, and artifact
format are not yet specified.

## Open design questions

- What is the recipe format?
- What source verification is mandatory?
- How are build dependencies declared and supplied?
- What level of build isolation is required?
- Can one recipe produce multiple packages?
- What reproducibility guarantees are required?
- What metadata must Build record for provenance and later inspection?
