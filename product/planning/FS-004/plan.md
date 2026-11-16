# FS-004 — Technical Plan: Stage 1C Native Buildroot Completion

## Objective and starting state

Complete DP-006 Stage 1C, beginning from accepted FS-003 at `2d2f3773c208e7783efa3e2160f2fd524cf5d91a`. FS-003 already supplies validated handoff restoration, target-native recipe isolation, independent staging, fixed identity, Manage create/publish and local index verification for Sed 4.10. Preserve these interfaces and acceptance evidence. The product outcome is a package-derived native production environment, not merely an expanded Stage 1B reconstruction.

## Full package selection and dependency authority

The initial Stage 1C package set is fixed by Planning to the ten Stage 1B selections, two foundational Stage 1A selections, and one Distro-owned filesystem package. Preserve the accepted versions, source identities and SHA-256 digests, but use independently reviewed Stage 1C target-native recipes.

| Package | Version | Selection origin |
| --- | --- | --- |
| filesystem | 1 | Distro-owned filesystem definition |
| bash | 5.3 | Stage 1B |
| coreutils | 9.10 | Stage 1B |
| sed | 4.10 | Stage 1B |
| grep | 3.12 | Stage 1B |
| gawk | 5.4.0 | Stage 1B |
| make | 4.4.1 | Stage 1B |
| diffutils | 3.12 | Stage 1B |
| tar | 1.35 | Stage 1B |
| binutils | 2.47 | Stage 1B |
| gcc | 16.2.0 | Stage 1B |
| linux | 7.1.8 | Stage 1A, headers-only payload |
| glibc | 2.44 | Stage 1A, native libc payload |

The exact source checksums are those in the accepted Stage 1B `cross-chroot.yaml` and Stage 1A `cross-toolchain.yaml` lists. GCC retains its selected GMP 6.3.0, MPFR 4.2.2 and MPC 1.4.1 supplements. Supplements do not automatically become separate package identities.

Build shall create a distinct Stage 1C selection for these thirteen payload-bearing packages. Linux headers must be available before native Glibc construction. Glibc must be freshly constructed and independently staged, providing the target runtime, dynamic loader and development files required by the managed production environment. Stage 1A recipes are cross-compilation references and shall not be executed unchanged as Stage 1C-native recipes.

The `distro-buildroot` metapackage is a separate, payload-free identity selecting the reviewed package closure through manifest-owned install relationships. Do not use a package-list-generated dependency graph as a competing authority.

The representative production workload is rebuilding Sed 4.10 from verified source using the normal Build execution path, with isolated staging and Manage package creation/publication.

The thirteen selected payload packages are not automatically proof of dependency closure.

The `filesystem` package has initial selected identity `(filesystem, 1, x86_64, 1)` and is a Distro-owned local-source package, not an upstream source archive. Its one authoritative package manifest resides under `product/src/build/packages/`. The Stage 1C list selects version `1` and its directly executed Bash recipe. Build verifies that the selected local source definition and recipe are regular checked-in files from the selected repository revision and records their content digests in the build evidence. Neither a fictitious upstream URL/checksum nor an unverified mutable working-tree input may substitute for this identity. The existing upstream-archive source model remains unchanged for all other selections; introduce an explicit local-source variant in the shared selector, never a `filesystem` name-based exception or parallel recipe engine. The local source variant is a bounded extension for Distro-maintained definitions; if it cannot be represented under DP-003, return to Design before implementing it.

Build's selected `filesystem` recipe deterministically creates a fresh independent DESTDIR payload; it does not execute a package installation through Manage or write package archive bytes. The explicit real directories and their selected modes are: `/etc` 0755, `/usr` 0755, `/usr/bin` 0755, `/usr/lib` 0755, `/usr/include` 0755, `/usr/share` 0755, `/var` 0755, `/var/lib` 0755, `/var/cache` 0755, `/var/log` 0755, `/var/tmp` 1777, `/tmp` 1777, `/run` 0755, `/dev` 0755, `/proc` 0555, and `/sys` 0555. The selected links are `/bin -> usr/bin`, `/sbin -> usr/bin`, `/lib -> usr/lib`, `/lib64 -> usr/lib`, `/usr/sbin -> bin`, and `/usr/lib64 -> lib`. These are target-root-relative links; the package never includes device nodes, mounts, dynamically populated runtime state, or host files. Modes and links must be checked against the staged package bytes and again after installation. Verify the selected `/lib64 -> usr/lib` and other merged-`/usr` links against the actual Glibc dynamic loader, ELF `PT_INTERP` strings, runtime shared-library resolution, and native GCC/binutils execution paths in the fresh managed root. A mismatch is a closure failure; do not silently move a loader, create an unowned workaround link, or import Stage 1B runtime files. This does not purport to establish Stage 2 system policy.

Manage's package format shall preserve explicit directory entries and modes as verifiable metadata. Existing FS-003 archives without directory entries remain readable. Multiple packages may declare the same directory only when its effective mode and type are compatible with the selected filesystem policy; conflicting directory modes are rejected rather than allowing incidental install order to decide them. Only one package may own each regular file or symlink. Resolve canonical target-root paths under the selected merged-`/usr` layout, reject unsafe ancestors and traversal, and never follow a link outside the target root. Manage applies the `filesystem` package before dependent payloads as part of a resolved installation plan, not through a hidden name-based special case. The manifest-derived install relationships of `distro-buildroot` and of the dependent packages must establish the required filesystem selection; installation order alone does not create undeclared dependency meaning.

The selected filesystem directory hierarchy does not by itself
establish every eventual Stage 2 filesystem policy. If an additional
layout decision becomes necessary for Stage 1C, return to Planning.

The thirteen selected payload packages are not automatically proof of dependency closure. Verify executable interpreters, libraries, compiler support files, development headers and all selected build-tool requirements in the fresh Manage-installed root. If independent verification demonstrates an additional necessary package or unresolved filesystem policy, return to Planning rather than copying files from Stage 1B or silently expanding the selection.

The current FS-003 Stage 1C implementation accepts only Sed. Do not expand its executable YAML selection until the generic multi-package runner and corresponding native recipes are introduced together in Build. Retain FS-003 validation during that transition.

Build shall resolve concrete selected versions, distinguish build-tool from install-relevant relationships, reject absent, ambiguous or cyclic dependencies, and derive deterministic construction order from authoritative manifests. No parallel dependency authority or package-specific branching is permitted in the Build controller.

## Pending Design amendment and baseline control

The Distro-maintained local-source model and generalized selected-version identity are proposed by DP-003/DP-005 changes on this branch at `c200cd9612d429fc0b59e9bb0548ebe39807750e`. They are not yet part of the accepted Design revision pinned by FS-004. Do not treat the proposed Design amendment as an accepted implementation authorization until it is intentionally integrated into `main` according to repository governance. Once accepted, update FS-004's exact `design_revision` and selected-revision narrative to the verified accepted commit, without changing the historical FS-003 baseline reference. Re-run Semantic Planning Review against that exact Design before Build activation. Mechanical Validation cannot substitute for this acceptance step.

## Manifest dependency categories and bootstrap resolution

Use the accepted DP-003 categories as distinct manifest-owned fields: `build_tools`, `build_link_dependencies`, and `runtime_dependencies`. The first category affects construction prerequisites but does not enter installed package relationships solely because it was needed to build. Both build-link and runtime categories produce explicitly selected install relationships. Resolve all names to exact selected versions/identities using the current stage list and its verified imported-provider capability set. Missing names, version conflicts, ambiguous selections and dependency cycles are errors. A verified Stage 1B capability can satisfy construction-time prerequisites while bootstrapping, but cannot satisfy any dependency in the separately installed published closure. Construction scheduling may use verified imported capabilities and selected construction results; installation closure uses only published package identities. Treat construction and installation as separate directed graphs. Construction ordering may contain imported Stage 1B capability edges and must reject unresolved dependencies and cycles after accounting for those verified imported providers. The final installed graph must be resolved solely from selected published package identities and independently reject missing edges and cycles; imported capability edges do not become installed relationships. In particular, construction of Glibc using the verified Stage 1B compiler and construction of native GCC against the selected Glibc must not be mistaken for a final GCC/Glibc installation cycle. If the manifest-declared installed graph does contain a true cycle, resolve it explicitly through Planning rather than silently suppressing an edge. Do not infer manifest dependency meaning from package lists, ELF audits, or recipes.

For backward compatibility, the legacy manifest `dependencies` field remains readable by existing Stage 1A/1B/FS-003 code, but Stage 1C publication must require explicit classification of every selected package dependency before production. The migration must not automatically interpret legacy dependencies as install dependencies or silently drop an install-relevant edge. Reject conflicting simultaneous legacy and categorized definitions unless an explicit compatibility rule proves equivalent meaning. The source-free `filesystem` selection and the empty-payload `distro-buildroot` selection use the same manifest/list/recipe and Build-to-Manage boundaries, with type-appropriate verification rather than fabricated archives.

## Coherent collection selection protocol

Continue to allow Manage's ordinary `create` and `publish` operations to place independently verified immutable artifacts and individual package records in its repository. These operations do not advertise a completed `distro-buildroot`. A separate candidate selection document names an exact, unambiguous set of package identities and corresponding repository artifact digests, including `filesystem`, `glibc`, Linux headers, the ten Stage 1B-selected packages, and the `distro-buildroot` metapackage. The candidate must resolve its install relationships exclusively from verified Manage records and be rejected if any member is absent, ambiguous, corrupt, ownership-conflicting, or insufficient for the selected closure.

Use the normal Manage resolver/installer to install this candidate into a fresh private root, then the ordinary Build root provider and native recipe executor to build and independently package Sed 4.10 without access to Stage 1B or the bootstrap construction workspace. The representative Sed 4.10 rebuild must not overwrite the immutable selected bootstrap Sed package identity. Produce its verification result in an isolated verification repository with a separately selected packaging revision or other explicitly distinct immutable identity; do not mutate the candidate closure while testing it. Only after this succeeds does Manage atomically replace the authoritative completed-collection selection pointer or file with one identifying the exact verified candidate. The authoritative repository package index may already contain individually selectable packages, but the completed-collection selector must never point at unverified closure. A local single-writer lock, same-filesystem temporary file, fsync of data/parent directory, and atomic rename protect promotion. Failures before promotion preserve the last usable complete selection; post-promotion durability/cleanup errors require explicit state verification, not assumed rollback or automatic retry. A candidate manifest or test evidence is not itself a second publisher or package artifact.

## Generic native package production

Refactor `product/src/build/bootstrap/distro_buildroot.py` to loop over selected steps using the existing Build selection, source verification and `native_recipe_command` execution mode. Construct each package from a verified Stage 1B provider during initial bootstrap, with isolated build directories and fresh per-package DESTDIR payloads; no output may sweep in imported filesystem content. Supply every package's fixed `(name, version, architecture, revision)` identity and resolved install relationships in the established Build-to-Manage exchange. Retain Build/Manage separation: Build never writes package archives or repository index records itself. The root provider changes at production time, not the recipe execution engine.

## Package model and metapackage

Extend the versioned Manage package model compatibly to support valid empty-payload metapackages without weakening path/member checks for ordinary packages. Represent `distro-buildroot` as an ordinary identity with manifest-owned relationships selecting the complete package closure. Keep path ownership conflicts deterministic and reject unsafe archive members and target escapes. Define and test the required merged-`/usr` layout links and their ownership before installing packages; do not silently create unowned filesystem repair links. If the existing repo schema cannot represent the selected collection atomically and accurately, evolve its versioned schema and reader deliberately, preserving FS-003 package compatibility or providing an explicit migration.

## Manage dependency resolution and fresh-root installation

Introduce a bounded Manage installation operation with a clear CLI (for example `install --repo <repo> --root <new-root> --package distro-buildroot`) and an installed-state database distinct from the available-package repository index. Resolve an exact, unambiguous collection using authoritative repository records and selected dependencies; verify all archive digests, contents, link targets and ownership before applying any package. Construct the new root privately then atomically promote completion state; never present partial application as installed. Preserve explicit package ownership and record selected identities, dependency relationships, integrity references and owned paths. Handle non-directory conflicts and symlink ancestors without following target-root escapes. For FS-004 a fresh empty installation root is sufficient; upgrades, removals and general rollback are excluded.

## Coherent publication and closure gate

Publishing individually valid package artifacts must not advertise `distro-buildroot` as a complete selectable collection. Produce a candidate complete collection, verify package relationships, payload integrity, layout, installation and representative execution, and only then promote a coherent authoritative selection. A failed or interrupted candidate must leave any previously usable authoritative selection unchanged. For the first local single-writer implementation, use bounded locking and atomic index/selection promotion. Preserve diagnostics for failures after promotion; do not mistake them for clean rollback.

## Production Build consumer and independent proof

Use the same target-native sandbox and directly executed Bash recipe path in both cases: Stage 1B handoff root provider during bootstrap, Manage-installed root provider during ordinary Build. Execute a representative selected native package build within an independently installed `distro-buildroot` collection, with explicit source and build mounts, clear environment, isolated writable DESTDIR and no host tools/libraries. The host may orchestrate source retrieval and isolation, but must not satisfy native construction requirements. Verify ELF interpreter/dependency closure, staged executable functionality, package creation and repository publication. Perform a fresh-root test from repository bytes alone, with original Stage 1B and construction workspace unavailable.

## Validation and milestone ordering

1. Resolve and review package list/recipes, categorized dependencies, filesystem layout and representative workload. Return to Planning if closure requires a consequential new design decision.
2. Implement generic multi-package Build selection/staging and fail-closed native execution; test independent package outputs and existing FS-003 behavior.
3. Extend Manage package metadata for empty metapackages and implement local dependency resolution, fresh-root safe installation and installed state.
4. Implement candidate collection closure verification and coherent promotion; test corrupt/missing artifacts, ownership conflicts, unsafe links, missing dependencies, cycles, interrupted install/publish and stale locks.
5. Prove a qualified-host full native build and then independently install and execute a native build from managed package outputs; register active mechanical task bindings, run canonical `scripts/validate`, conduct Semantic Build Review and accept only by intentional integration into `main`.

## Decision control

Do not mark closure complete using Stage 1B files, host tools, a package tarball copied into a root without Manage, or an alternate Stage 1C-only install path. Do not silently extend scope to Stage 2 or final self-replication. If native recipe requirements, manifest dependency categories, merged-`/usr` ownership, or coherent collection publication cannot be realized under accepted DP-003 through DP-006 meaning, return to Design/Planning before Build changes.
