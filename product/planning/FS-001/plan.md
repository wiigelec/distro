# FS-001 — Technical Plan: Cross-Toolchain Construction

## Goal and Shape

Implement Stage 1A on the existing Build surface, not as a separate bootstrap builder. The command `product/scripts/build cross-toolchain --root <rootdir>` selects host execution and the `cross-toolchain` list. Build uses the shared manifest/list/Bash-recipe pipeline; the stage adapter supplies only stage selection, execution context and artifact production.

## Workspace and Data Flow

The selected `--root` is a workspace directory, not the install prefix:

```text
rootdir/
  build/       source extraction and compilation work
  root/        installed target / filesystem hierarchy
  artifacts/   archived contents of root/
```

The workflow resolves package selections, verifies inputs, extracts sources into build work, prepares package-specific build directories, runs selected Bash recipes directly on the host with an explicit context, installs their resulting files into the `root/` hierarchy, validates the result and archives the installed filesystem only. The archive is the handoff contract for Stage 1B; it must not depend on `build/` being retained.

## Package Model

- Under `product/src/build/packages/`, each package has one authoritative YAML manifest defining identity, upstream archive location/name template, source verification information and package dependencies. Manifests do not select versions or contain construction commands.
- Under `product/src/build/lists/`, the Stage 1A list selects each package's exact version and Stage 1A Bash recipe. A list does not redefine dependencies or embed build instructions.
- Under `product/src/build/recipes/`, ordinary executable Bash scripts perform package-specific configure/build/install operations. A recipe can be run independently when given the documented context. No generated recipe translation, JSON command interpreter or package-specific command table is introduced.
- Use a minimal Stage 1A package selection sufficient for an initial target assembler/linker, compiler, Linux API headers and C library interface. The prototype's Binutils/GCC/Linux headers/glibc exploration and LFS Chapter 5 are references for selecting and verifying that closure, not automatic authority for versions, commands or acceptance criteria. Exact version strings and the reproducible tested list are committed as project data before a completed FS-001 build is claimed.

## Dependencies and Order

The Stage 1A list provides complete explicit version selections for every selected package and applicable dependencies. Build checks that manifest-declared requirements needed in Stage 1A resolve to these selections or to a documented host-provided tool capability. It executes packages in a deterministic order satisfying relevant prerequisites, rejects missing or cyclic requirements when relevant, and does not move dependency declarations into recipes or lists. The precise minimal YAML representation of context-sensitive dependency rules is chosen only as required by the selected set; do not implement a general condition engine absent a demonstrated need.

## Execution Contract

Build supplies a small, documented environment to each Bash recipe: source directory, separate package build directory, installed filesystem root, target triplet and selected package identity/version. Stage 1A executes package construction on the foreign host; target toolchain binaries and files are installed beneath the selected filesystem root rather than into the host OS. Recipes own compiler flags, configure options, patches and package-specific steps. Build must not parse or generate recipe instructions. Host assumptions needed for the selected toolchain are explicit and checked before irreversible construction.

## Source and Failure Semantics

Resolve exact source URLs from the authoritative manifest and list version, download archives, verify against manifest-defined integrity information before extraction, and fail closed on missing or failed verification. Build does not silently discover newer versions. A failed package operation fails the Stage 1A command; a partial root or archive must not be reported as a successful handoff. Whether a workspace is reusable and the precise safe cleanup/retry algorithm are Build-level choices, provided stale output cannot be mistaken for success and unrelated files are preserved.

## Artifact and Functional Verification

The produced archive represents the installed root filesystem, with filesystem structure and symlinks preserved as required for Stage 1B consumption. Construction completion requires more than successful recipe exit codes: exercise the cross compiler/toolchain to create target objects, check relevant target/ELF properties, and test linking against the constructed target interface as far as is feasible in Stage 1A. Native execution of target programs or complete Stage 1B is not required here. Keep host-tool reliance explicit rather than claiming foreign-host independence in Stage 1A, which by Design is host-executed.

## Validation and Lifecycle

Planning classifies obligations below; Build registers project-native tasks for every active mechanical (`M`/`B`) requirement and binds them in `product/validation/requirement-evaluation.json`. Run canonical `./scripts/validate` as the repository mechanical gate. Also perform semantic Build Review against the accepted Design, this FS scope and the full Plan. Mechanical passing cannot substitute for semantic acceptance, and no direct integration into `main` occurs before satisfactory review.

## Implementation Sequencing

Implement the minimal package model and Stage 1A execution contract, then working recipes and artifact export, then functional checks and requirement bindings. Keep the engine shared in architecture but implement only the host execution capability exercised by FS-001; isolated buildroot execution remains later work.
