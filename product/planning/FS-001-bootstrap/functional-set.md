# FS-001 — Distro Bootstrap

## Design binding

- **design_revision:** `12e71d53fde329b16b14ed8103136443696efa70`
- **selected controlling design:** `product/design/bootstrap.md`
- **related applicable design:** `product/design/architecture.md`, `product/design/build.md`, `product/design/manage.md`, `product/design/install.md`, `product/design/interfaces.md`, `product/design/package-model.md`, `product/design/package-metadata.md`, `product/design/package-database.md`, `product/design/autonomous-build.md`.

The revision binds the *entire accepted Design corpus* as of that commit; the selected portion gives the scope of this Functional Set. Prototypes are non-normative evidence only.

## Purpose and result

Bootstrap a Distro-native system from a qualified Arch Linux host, replacing foreign-host construction dependencies with native Distro capabilities. Complete a managed native Build chroot, a bootable package collection capable of constructing and operating that Build chroot, and an installed VM that independently boots, creates a Build chroot, builds Distro packages, and acts as a freshly qualified bootstrap host to repeat M1 and M2.

## Milestones

1. **M1 — Cross-toolchain:** qualify the Arch host and select verified sources; build and validate a Distro-targeting cross-toolchain.
2. **M2 — Temporary tools:** establish a Distro-native-capable temporary tools chroot for native construction.
3. **M3 — Bootstrap-chroot Distro packages:** create Distro package artifacts through native construction and use Manage to assemble and exercise a definitive independent Build chroot.
4. **M4 — Bootable package set:** produce a bootable Distro package collection that *also includes sufficient capabilities to create the managed Distro Build chroot and build Distro packages*.
5. **M5 — Installed VM:** use Install and Manage to install M4 packages and boot through GRUB to systemd userspace; inside the installed Distro VM, clone the Distro repository and execute its normal bootstrap with Distro acting as the new foreign host, constructing and validating a fresh M1 cross-toolchain and M2 with full generation-A-to-generation-B self-replication. Separately demonstrate that Manage can create a definitive Build chroot and native Build can produce a representative Distro package.

Milestones are internal acceptance checkpoints of **one** Functional Set, not separate Functional Sets. M5 proves the integrated result; milestone checks alone do not establish Functional Set acceptance.

## Included

Host qualification without host package modification; source/version resolution and frozen execution-local provenance; isolated cross and temporary native construction; creation of interoperable Distro package artifacts and initial publication state; minimum Build/Manage/Install operations needed for bootstrap; definitive managed Build chroot; minimal bootable package set; installed bootable VM capable of acting as its own new M1→M2 bootstrap host; native build and source/artifact validation evidence; reproducible rerun/resumption behavior to the extent required to validate the same resolved bootstrap inputs.

## Explicitly deferred

Full ongoing autonomous source tracking and scheduling; full future Manage feature coverage not necessary for bootstrap; interactive/general-purpose installation UX; additional architectures, firmware modes, partition layouts, networking profiles, graphical environments, mirror federation and public repository services. Deferral cannot weaken accepted package identity, metadata authority, publication consistency, or independent native build capability in the behavior actually implemented.

## Planning boundary

The Plan shall resolve material technical choices necessary for a testable five-milestone execution, including host/toolchain isolation, source integrity, package artifact and database representations, initial dependency closure, build-root provisioning, VM boot/install mechanism, and failed-operation safety. Choices not settled by Design are Planning decisions and do not amend Design meaning.
