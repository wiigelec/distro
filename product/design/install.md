# Install

## Role

Install is the distro's system installer.

It orchestrates creation of a usable target system.

## Responsibilities

Install is responsible for installation workflow, including the following
categories of behavior as they are designed:

- preparing or validating an installation target;
- preparing filesystems and mounts;
- selecting an installable system profile or package set;
- invoking Manage against the target root;
- writing installation-time system configuration;
- configuring the installed system sufficiently for first boot;
- arranging boot support when required;
- reporting installation success or failure.

The exact scope of disk partitioning, interactive configuration, bootloader
support, and installation profiles is not yet fixed.

## Package installation rule

Install must not maintain a separate package installation implementation.

When packages are installed into the target, Install delegates that operation
to Manage.

Conceptually:

```text
installation choices
        |
        v
      Install
        |
        +---- target preparation
        |
        +----> Manage against target root
        |          |
        |          v
        |    installed package state
        |
        +---- system configuration
        |
        v
 usable installed system
```

The diagram describes responsibility, not a final CLI.

## Boundary with Build

Install operates on package artifacts made available locally or through the
package distribution system.

Build owns transformation of source material and recipes into package artifacts.
Install does not compile packages during a normal installation.

## Boundary with Manage

Install determines installation workflow, package selection, and
installation-wide target configuration.

Manage determines how package state is changed inside the target and owns any
package-local lifecycle consequences defined by the package-management model.

Install owns machine-level policy and configuration selected as part of the
installation, such as categories including machine identity, users, locale,
networking policy, and boot configuration. The exact supported settings remain
open design questions.

## Open design questions

- Does Install partition disks itself or operate on prepared targets first?
- Which installation profiles or package sets exist?
- How is target-root entry represented?
- How are users, locale, timezone, hostname, and networking configured?
- Which bootloaders and firmware modes are supported?
- Which parts of installation must be non-interactive or scriptable?
- What recovery behavior is required after a partially completed install?
