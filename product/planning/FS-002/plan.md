# FS-002 — Technical Plan: Cross-Chroot Temporary Tools

## Goal and implementation boundary

Use the existing Build engine to realize the Stage 1B `cross-chroot` operation defined by DP-002. The primary *technical reference* is the temporary-tools implementation on `wiigelec/distro-proto` branch `proto/distro-bootstrap-chroot` (manifest, recipes, package runner, integration and smoke tests). It supplies candidate implementation approaches, not Design or requirement authority. Do not implement a second package driver or copy the prototype's JSON recipe language. Stage 1C and native self-replication are out of scope.

## Stage invocation and filesystem

Support `./product/scripts/build cross-chroot --root <rootdir> --cross-toolchain <path-to-cross-toolchain.tar.xz>`. `--root` designates a fresh workspace containing `build/` (verified sources and compilation), `root/` (installed target filesystem) and `artifacts/` (output handoff). Consume the existing Stage 1A `cross-toolchain.json` from the archive's directory; require Stage 1A's schema, artifact identity, target `x86_64-distro-linux-gnu`, mount contract, successful functional and relocation verification, and matching file size/SHA-256. An archive by itself is not a complete handoff. Verify safe archive entries before extracting into a fresh target root; do not use Stage 1A's original build directory or absolute host paths.

The target root is writable only in the authorized sandbox-visible installation tree `/toolchain`, with verified sources and per-step builds under `/work`. Keep the existing controlled host execution model: read-only host tool/library exposure, sanitized environment, isolated temporary directories, no recipe network, and fail-closed Bubblewrap setup. Host-executed cross-compilation must not require entering the target chroot as the build executor. Target-native execution in an isolated test root is a *verification* operation.

## Selection and sources

Create the distinct `product/src/build/bootstrap/cross-chroot/lists/cross-chroot.yaml`. Reuse the authoritative manifests for `binutils` and `gcc`; add missing manifests to `product/src/build/packages/` for `bash`, `coreutils`, `sed`, `grep`, `gawk`, `make`, `diffutils`, and `tar`. Each manifest owns source URL template, verification type, and true package dependencies; the list alone owns selected versions/checksums and step-appropriate recipes. Existing Stage 1A selections remain unchanged. A required dependency already provided by the validated Stage 1A import may be satisfied by that imported prerequisite if explicitly modeled and checked; it must not trigger a redundant cross-toolchain build. Preserve the authoritative identity of `binutils` and `gcc`, even for their native-tool recipe selections.

Start with the ten *ordered construction steps* exercised by the prototype:

1. bash 5.3
2. coreutils 9.10
3. sed 4.10
4. grep 3.12
5. gawk 5.4.0
6. make 4.4.1
7. diffutils 3.12
8. tar 1.35
9. binutils 2.47 (native tool selection)
10. gcc 16.2.0 (native compiler selection)

Use independently checked SHA-256 values for the selected upstream archives. The prototype's GCC in-tree prerequisite sources and versions differ from the accepted Stage 1A selections; reuse Stage 1A's supported, verified GMP/MPFR/MPC source model and resolve any needed Stage 1B selection explicitly, not via unchecked recipe downloads. Do not infer that the prototype's package selection already proves Stage 1C sufficiency; the FS-002 functional gate must establish the specific required native capabilities.

## Bash recipes and installation

Create one directly executed Bash recipe per selected step in `product/src/build/bootstrap/cross-chroot/recipes/`. Translate the prototype's configure, build, installation and essential environment choices into ordinary scripts using existing `DISTRO_SOURCE_DIR`, `DISTRO_BUILD_DIR`, `DISTRO_ROOT_DIR`, `DISTRO_TOOLS_DIR`, `DISTRO_TARGET`, `DISTRO_PACKAGE_VERSION`, `DISTRO_STEP_ID`, and `DISTRO_JOBS` context. Bind cross-compilers, target sysroot and installation paths to the stable sandbox-visible locations. Do not add package-name conditionals or an interpreted steps language to the Build engine.

The imported toolchain and new package outputs share the target root. Record a clear collision policy: reject unrecognized overwrites; allow only explicitly verified, package-justified ownership transitions (notably compiler-private GCC files); preserve imported files which a newly built package must not replace. The prototype's Binutils plugin exclusion and GCC private backend transition are technical reference candidates and require verification in the adapted filesystem layout. Ensure installation paths do not write into the host filesystem. Preserve relevant target `/usr` layout and symlink semantics.

## Verification and output

Check source digests, selected dependency order, each recipe's exit status, expected installed programs and target ELF interpreter/library closure. In a target-root-isolated verification environment, run the target-native shell and representative utilities; compile, link, and execute minimal native C and C++ programs with the installed GCC/Binutils/libc, proving no undeclared host userspace dependencies. Verify the target filesystem still supplies the capability needed to start Stage 1C; native package rebuilding is not part of this gate.

Package only installed `root/` contents into `artifacts/cross-chroot.tar.xz` (PAX-compatible tar.xz). Create `artifacts/cross-chroot.json` as the completion marker, recording artifact identity, size/SHA-256, parent Stage 1A artifact digest, exact package selections, target and mount contract, source provenance and successful functional/relocation checks. Extract and verify an unpublished candidate archive in a distinct workspace while excluding the original build location; publish archive first and metadata last. Never accept a partial/stale handoff after failure. Reuse Stage 1A archive safety and handoff primitives where appropriate without weakening their checks.

## Implementation and evaluation

Keep changes inside existing product-owned namespaces. Ordinary Build implementation choices include narrow CLI dispatch, the stage orchestrator, helper reuse, and validation code. Create mechanical evaluation tasks and exact bindings for every active mechanically evaluated FS-002 requirement in the product Requirement Evaluation Manifest. Invoke canonical `scripts/validate` and perform semantic Build Review against both this Planning result and accepted Product Design. Do not treat a test pass, pushed branch, or PR as Acceptance; only intentional integration into `main` is Acceptance.

## Scope and decision control

If target filesystem layout, GCC ownership transitions, manifest dependency modeling, or Stage 1C readiness cannot be resolved faithfully within these constraints, return to Planning rather than silently expanding FS-002. Do not add a generic package execution engine, chroot construction machinery for Stage 1C, or additional package inventory absent a demonstrated FS-002 need.
