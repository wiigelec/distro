# FS-003 — Technical Plan: Stage 1C Initial Native Package Production

## Goal and boundary

Realize one reusable end-to-end Stage 1C package-production slice under the accepted DP-001 through DP-006 architecture. The result is one independently verifiable native package published by standard Manage operations, not a complete `distro-buildroot` closure. The selected first package is GNU Sed 4.10, using the existing authoritative `sed` manifest and the source checksum already selected for FS-002. The Stage 1B Sed installation is construction input only; the FS-003 Sed package must result from a fresh target-native build and independently staged output.

## Invocation and verified Bootstrap input

Support `./product/scripts/build distro-buildroot --root <rootdir> --cross-chroot <cross-chroot.tar.xz>`. Preserve the existing empty-workspace discipline and separate build, imported construction root, per-package staging, and artifact/repository locations. Require a matching `cross-chroot.json` alongside the archive. Validate Stage 1B artifact identity, target, mount contract, successful functional and relocation evidence, size and SHA-256 before safe extraction. Reject malicious archive paths, unsafe entries, root escapes and mismatched metadata. Never consult the Stage 1B construction workspace after restoring its handoff.

## Shared native buildroot execution

Extend Build's common stage selection and recipe execution path instead of introducing a second Stage 1C engine. Add a distinct `bootstrap/distro-buildroot/lists/` selection and native Bash recipe, retaining the existing `sed` manifest as the authority for source and dependencies. Select Sed 4.10 with SHA-256 `b8e72182b2ec96a3574e2998c47b7aaa64cc20ce000d8e9ac313cc07cecf28c7`. Verify source bytes through the existing source acquisition mechanism. Stage 1B provides initial verified tools and libraries for construction but does not create package identities or installed Manage state.

Run the selected Bash recipe as a target-native process in a fail-closed isolated root. The foreign host may control setup and verification but must not supply undeclared executable tools or runtime libraries to the native construction process. Provide only explicit writable locations for source/build work and the package installation staging root, controlled environment and search paths, and required virtual system mounts. Keep host userspace outside the native process dependency closure; failure to establish isolation aborts. The execution configuration and recipe invocation are reusable for later package-based production buildroots; only the provider of the root differs. Test that the execution mode works after restoring the Stage 1B artifact into another workspace.

The Sed recipe configures, compiles and installs using target-native tools; installation must honor a distinct destination directory rather than replacing files in the imported construction root. A package that cannot be independently staged under the supported interface fails the slice instead of falling back to collecting the modified construction root. Do not use FS-002 host-executed cross-compilation recipes as native recipes.

## Selected identity and Build-to-Manage handoff

For the initial selection use identity `(sed, 4.10, x86_64, 1)` where the packaging revision `1` is the explicit initial selection for this Functional Set. Build fixes the complete selected identity before invoking Manage. Build supplies an isolated per-package filesystem, the fixed identity, and the manifest-derived selected install-relevant relationships. Manage verifies but does not reselect identity, interpret the recipe, or invent dependencies. The Sed manifest currently declares no package dependencies; an empty install-relevant relationship set is valid for this bounded artifact and does not assert that the eventual production closure is dependency-free.

## Package artifact and local repository

Use one portable PAX-compatible tar.xz package archive containing an installable target-root-relative payload and embedded identity metadata. Use canonical JSON for the authoritative repository index and package records, recording identity, manifest-derived relationships, installed non-directory path inventory, artifact locator, size and SHA-256. A package record is not an installed-state database. Keep payload files separate from package control metadata; reject absolute, traversal, device and unsupported special archive entries, and links that escape their installation root. Directory sharing is allowed; non-directory path ownership collisions are rejected when checked against any existing authoritative selection.

Manage exposes the DP-004 `create --package <name> --build <path>` and `publish --package <name> --repo <path>` operations. The `--build` directory is the standard Build-to-Manage exchange containing the staged payload and selected identity/relationship description; `create` produces an artifact suitable for later `publish`. Build orchestrates those operations but must not serialize package archives or mutate the repository index itself. Package archive and index serialization details may be implemented as small versioned formats with explicit strict parsers, avoiding an independent package model.

Publish the artifact to a local repository before atomically replacing an authoritative index. Verify artifact size/hash and referenced files before promoting the index. Failed create or publish must not advertise a missing or partial artifact, and must leave an existing usable selection intact. For this single-writer initial slice, serialize publisher mutations with an exclusive repository lock; fail closed on concurrent/conflicting publication. Do not mark the `distro-buildroot` metapackage or a package closure as complete or selectable.

## Independent verification and evidence

Verify the constructed Sed binary and its ELF runtime resolution inside the isolated target environment. Then, without access to the original source/build workspace, independently open the created package and repository index; check exact identity, path inventory, embedded metadata, stored relationships, archive digest and size, and ability to safely restore the payload into a fresh verification directory. Confirm that no imported Stage 1B files were swept into the package. Test negative cases for missing/mismatched input metadata, unsafe archive paths, attempted host userspace exposure, staging-root pollution, package ownership conflicts, partial publication and interrupted candidate creation. A representative single-package build is evidence for this slice, not the full Stage 1C closure.

## Implementation, validation and review

Keep implementation under the established `product/src/build`, `product/src/manage`, `product/scripts`, Bootstrap stage selections/recipes and product validation surfaces. Add mechanical tasks with exact bindings only when their corresponding normative requirements become active; required task names and implementation stay with Build. Keep inactive mechanically classified obligations inactive until enforcement exists, as in FS-002's initial Planning state. Run canonical `scripts/validate`, qualified-host native execution and independent artifact checks, then conduct Semantic Build Review against this Plan, requirements and the consumed Design revision. Only intentional integration into `main` is Acceptance.

## Decision control

If the selected package cannot be built and independently staged with the existing accepted package model, or the design cannot be preserved without adding installation, full dependency-closure resolution or an alternative publisher, return to Planning. Do not expand FS-003 silently.
