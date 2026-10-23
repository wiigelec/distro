# Bootstrap

## Purpose

Bootstrap establishes Distro from a qualified foreign Linux host. It creates the initial Distro-native build capabilities and package collections needed to operate independently, including a managed build environment and a minimal bootable system.

Bootstrap is an infrequent initialization process, not an ongoing package-maintenance mechanism. Once the initial Distro package baseline is established, the normal package lifecycle assumes responsibility for discovering and selecting future versions, maintaining recipes, producing updates, and publishing packages.

## Foreign Host and Source Selection

Bootstrap initially operates on Arch Linux. The foreign host provides the existing compiler, toolchain, libraries, utilities, and execution substrate required to begin construction.

The qualified foreign host also serves as the known-working package/version reference configuration for the complete initial bootstrap, not solely as a source of tools for the first construction stage. Before construction, bootstrap identifies the full selected package and recursive build/runtime dependency closure needed through the bootable result, requires corresponding packages to be installed on that host, and qualifies their installed versions and upstream-source mappings as one execution-local snapshot. A missing or ambiguous counterpart makes the reference incomplete and prevents construction until it is corrected. This intentional whole-configuration requirement keeps the initial source selection grounded in one integrated host configuration rather than an arbitrary mixture of upstream versions. It does not guarantee that unpatched upstream sources or the resulting Distro packages are compatible: the constructed environments require their own validation. The snapshot is an initialization reference, not ongoing package-version authority.

Bootstrap checks the foreign host for the packages and capabilities required for construction. If a required package is missing or incompatible, bootstrap identifies the deficiency and reports the corrective action needed from the end user. The end user is responsible for installing or correcting host packages and rerunning qualification. Bootstrap does not install, upgrade, remove, or otherwise modify packages on the foreign host.

Once the host satisfies its prerequisites, bootstrap discovers the installed versions of required host packages and uses them to select corresponding upstream source releases for Distro. Required bootstrap packages absent from the host must be installed by the end user before their versions are resolved. Distribution-specific package release identifiers may differ from upstream source versions and must be mapped accordingly.

Bootstrap does not maintain a repository-pinned bootstrap package-version catalog. Each new bootstrap derives its initial choices from its qualified foreign host.

The selected source versions, identities, and verification evidence remain consistent throughout an individual bootstrap execution, including resumption. They are retained as local construction state and evidence rather than becoming ongoing repository version policy.

The discovered host configuration is a starting point, not proof of compatibility: bootstrap must qualify the host and validate the resolved sources and resulting environments.

## Construction and Trust Boundary

Bootstrap progressively replaces reliance on foreign-host build tools with Distro-native capabilities.

The foreign host first supports construction of a Distro-targeting cross-toolchain and its required runtime interfaces. That toolchain is used to produce temporary Distro-targeted tools and libraries, establishing a native-capable temporary bootstrap chroot.

The temporary chroot then supports production of the Distro-native packages needed for independent build and operating environments.

Declared foreign-host tools may participate in intermediate construction. The resulting independent Distro environments must not rely on undeclared foreign-host userspace files or runtime dependencies. The temporary bootstrap filesystem is a construction environment, not an installed Distro system or a source of untracked final-system files.

## Native Package Collections

Bootstrap produces Distro-native package artifacts that can be consumed through the normal package interfaces. The final artifacts follow Distro's existing package identity, runtime metadata, integrity, ownership, and publication contracts; bootstrap does not define a competing permanent package format or package-management model.

One package collection establishes the definitive Build chroot, supplying the compiler, libraries, utilities, and dependency closure required to build subsequent Distro packages without foreign-host userspace dependencies.

Another package collection establishes a minimal bootable Distro system. It includes a Linux kernel, GRUB, systemd, essential userspace, and their necessary runtime dependencies.

The two collections may share packages but need not have identical inventories. Their common package-production origin does not eliminate their distinct purposes.

## Package Management and Installation

Bootstrap establishes the initial Manage and Install capabilities needed to consume the native package artifacts and construct Distro environments.

Manage applies package artifacts to target filesystems and maintains authoritative installed-package state. Install prepares an installation target, delegates package installation to Manage, and performs system-level configuration necessary for boot.

During early bootstrap, temporary mechanisms may populate intermediate construction roots before the native package-management capability exists. These mechanisms are transitional and do not constitute an alternative permanent package-management authority.

The definitive Build chroot is assembled from Distro-produced package artifacts, not by copying the temporary bootstrap root wholesale.

## Bootable System

The initial Distro operating environment is a minimal independently bootable virtual machine.

GRUB loads the Linux kernel, and systemd initializes and manages userspace. The system reaches a usable local operating environment without depending on the foreign host's userspace.

The initial bootstrap design does not prescribe a specific firmware mode, partition scheme, installer interface, or broader hardware-support policy. Those choices belong to subsequent technical planning, provided the intended independent boot capability is preserved.

The Build chroot and bootable system are separate environments; a Build chroot need not itself be bootable.

## Validation and Transition

Successful bootstrap establishes that the temporary native build environment can produce the initial package artifacts; that those artifacts can construct an independent Build chroot; that the Build chroot can build Distro packages without undeclared foreign-host userspace dependencies; and that the initial installed virtual machine can boot through GRUB into systemd-managed userspace.

Source provenance, environment inputs, package artifacts, dependencies, and validation evidence are retained sufficiently to inspect the bootstrap's result and distinguish temporary foreign-host assistance from native Distro output.

The bootstrap-produced package baseline is the starting point for Distro, not a permanent version constraint. Its adoption into normal operation preserves the separate authorities of the maintainer-declared Package Manifest, Build State, and published Package Database. Locally resolved bootstrap inputs and construction evidence do not themselves redefine package tracking policy or published package state. Following bootstrap, normal package lifecycle authority governs future upstream version selection, package changes, upgrades, and publication. Bootstrap does not continue tracking the foreign host.
