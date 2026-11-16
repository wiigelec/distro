# FS-004 — Technical Plan: Stage 1C Native Buildroot Completion

## Objective and starting state

Complete DP-006 Stage 1C, beginning from accepted FS-003 at `2d2f3773c208e7783efa3e2160f2fd524cf5d91a`. FS-003 already supplies validated handoff restoration, target-native recipe isolation, independent staging, fixed identity, Manage create/publish and local index verification for Sed 4.10. Preserve these interfaces and acceptance evidence. The product outcome is a package-derived native production environment, not merely an expanded Stage 1B reconstruction.

## Full package selection and dependency authority

Expand the existing Stage 1C list from one Sed step to a concrete, reviewed explicit-version package set sufficient for a selected representative production workload. The Stage 1B list (Bash, Coreutils, Sed, Grep, Gawk, Make, Diffutils, Tar, native Binutils, native GCC) is a reference, not proof of closure; select and independently package required glibc/runtime, headers, development inputs, supporting libraries, interpreters, extraction utilities and any other prerequisites. Review source checksums and native build recipes for every selection. The list owns versions/checksums and recipe selections; the shared authoritative package manifests alone own categorized dependency declarations. Resolve concrete selected versions, distinguish build-tool from install-relevant relationships, reject missing or ambiguous dependencies and dependency cycles, and derive a deterministic build order. Avoid hard-coded dependency graphs or package-specific branches in Build.

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
