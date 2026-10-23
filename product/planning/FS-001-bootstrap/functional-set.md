# FS-001 — Distro Bootstrap

## Design binding

- **design_revision:** `1a70607f80ee6014f261dceb5476e482b6ec0767`
- **selected controlling design:** `product/design/bootstrap.md`
- **related applicable design:** `product/design/architecture.md`, `product/design/build.md`, `product/design/manage.md`, `product/design/install.md`, `product/design/interfaces.md`, `product/design/package-model.md`, `product/design/package-metadata.md`, `product/design/package-database.md`, `product/design/autonomous-build.md`.

The revision binds the *entire accepted Design corpus* as of that commit; the selected portion gives the scope of this Functional Set. Prototypes are non-normative evidence only.

## Purpose and result

**Known-good reference configuration.** The initial Arch host is the known-working reference for the complete M1–M5 bootstrap package/version configuration, not merely a supplier of tools for M1. Before construction, preflight identifies and freezes one execution-local snapshot of the installed host counterparts and full versions for the entire selected bootstrap manifest and its recursive build/runtime dependency closure. Every required counterpart must be installed and unambiguously mapped to an available upstream source release; missing or ambiguous entries stop the bootstrap for user correction or reviewed mapping changes. This deliberate whole-manifest gate prevents construction from starting with an unqualified or internally inconsistent version selection. The snapshot supplies a reference for source selection, not a claim that unpatched upstream sources or future Distro packages have already been proven compatible; M1–M5 must independently establish their correctness. It is neither a repository-pinned version catalog nor ongoing package-version authority.

Bootstrap a Distro-native system from a qualified Arch Linux host, replacing foreign-host construction dependencies with native Distro capabilities. Complete a managed native Build chroot, a bootable package collection capable of constructing and operating that Build chroot, and an installed VM that independently boots and acts as a freshly qualified host to repeat M1 and prove full M2 self-replication. M3/M4 establish the managed Build-chroot and native package-building capability.

## Milestones

1. **M1 — Cross-toolchain:** qualify the Arch host and select verified sources; build and validate a Distro-targeting cross-toolchain.
2. **M2 — Temporary tools:** establish a Distro-native-capable temporary tools chroot for native construction.
3. **M3 — Bootstrap-chroot Distro packages:** create Distro package artifacts through native construction and use Manage to assemble and exercise a definitive independent Build chroot.
4. **M4 — Bootable package set:** produce a bootable Distro package collection that *also includes sufficient capabilities to create the managed Distro Build chroot and build Distro packages*.
5. **M5 — Installed VM:** use Install and Manage to install M4 packages and boot through GRUB to systemd userspace; inside the installed VM, clone the Distro repository and execute a fresh M1→M2 bootstrap using Distro as the foreign host. M5 passes when the newly constructed M2 environment completely rebuilds itself (generation A→B). M3/M4, rather than M5, own managed Build-chroot and native package-building acceptance.

Milestones are internal acceptance checkpoints of **one** Functional Set, not separate Functional Sets. M5 proves the integrated result; milestone checks alone do not establish Functional Set acceptance.

## Included

Host qualification without host package modification; source/version resolution and frozen execution-local provenance; isolated cross and temporary native construction; creation of interoperable Distro package artifacts and initial publication state; minimum Build/Manage/Install operations needed for bootstrap; definitive managed Build chroot; minimal bootable package set; installed bootable VM capable of acting as its own new M1→M2 bootstrap host; native build and source/artifact validation evidence; reproducible rerun/resumption behavior to the extent required to validate the same resolved bootstrap inputs.

## Explicitly deferred

Full ongoing autonomous source tracking and scheduling; full future Manage feature coverage not necessary for bootstrap; interactive/general-purpose installation UX; additional architectures, firmware modes, partition layouts, networking profiles, graphical environments, mirror federation and public repository services. Deferral cannot weaken accepted package identity, metadata authority, publication consistency, or independent native build capability in the behavior actually implemented.

## Planning boundary

The Plan shall resolve material technical choices necessary for a testable five-milestone execution, including host/toolchain isolation, source integrity, package artifact and database representations, initial dependency closure, build-root provisioning, VM boot/install mechanism, and failed-operation safety. Choices not settled by Design are Planning decisions and do not amend Design meaning.
