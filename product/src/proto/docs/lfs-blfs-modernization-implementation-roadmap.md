# LFS/BLFS Modernization Implementation Roadmap

## Objective

Modernize Linux From Scratch / Beyond Linux From Scratch so that validated distro state becomes authoritative and the instructional books, automated validation builds, and user-facing distro automation all consume the same source of truth.

The migration should preserve the educational value and visible behavior of the existing books while eliminating the current dependency on publication XML as executable package/build semantics.

## 1. Architectural contracts

The implementation begins by freezing the following boundaries.

```text
DEV LAYER
    authoritative package/system knowledge
    manifests
    discovery
    build/test/validation

PRESENTATION LAYER
    structural data
    editorial data
    validated package/system data
        ↓
    standardized document representation

USER AUTOMATION LAYER
    consumes validated dev definitions
    generates usable build scripts/plans
    plugins handle packaging/deployment
```

Core invariants:

1. Package definitions are version-independent.
2. Development and release manifests select versions.
3. A package enters management by appearing in the package-set manifest.
4. Discovery may run automatically or manually; behavior is identical.
5. Discovery proposes state. Validation promotes state.
6. Release manifests are frozen development-version snapshots.
7. Package identity is independent of build identity.
8. Document identity is independent of package identity.
9. Bootstrap builds are special; normal LFS and BLFS builds share one model.
10. Presentation never becomes authoritative build data.
11. User automation never maintains independent package recipes.
12. Generated scripts are artifacts, not source-of-truth definitions.

## 2. Logical data model

Define only the domain objects required by actual LFS/BLFS behavior:

```text
Package
Build
Procedure
Dependency
Collection
Profile
PackageSet
VersionManifest
ValidationResult

PresentationStructure
EditorialContent
CompiledDocument
```

The first schema should be driven by existing LFS/BLFS requirements rather than an attempt to model every future distribution use case.

Acceptance condition:

> Every semantic element required to build or render current LFS/BLFS has an explicit authoritative home.

## 3. Migration extractor

Build a temporary migration tool that converts current LFS/BLFS source into candidate normalized objects.

```text
current LFS/BLFS XML
        ↓
semantic extractor
        ↓
candidate normalized objects
```

Mechanically extract where reliable:

- package identities
- versions
- source URLs
- checksums
- sizes
- build metrics
- commands
- command privilege
- existing phase hints
- dependencies
- kernel options
- installed contents
- patch references
- configuration sections
- document hierarchy
- IDs and cross references

Ambiguous cases should be flagged for review instead of guessed.

The extractor is scaffolding. It must not become a permanent dependency of the new architecture.

## 4. Normalize LFS final-system packages first

Begin with normal final-system packages rather than bootstrap.

Initial representative packages:

```text
zlib
bash
coreutils
grep
gzip
make
```

Prove:

```text
version-independent package definition
+
development version manifest
        ↓
build engine
        ↓
equivalent installed result
```

Then expand until all final LFS packages run through the common normal package model.

## 5. Build the normal package executor

The normal executor becomes the shared engine for final LFS and BLFS.

```text
resolved package definition
        ↓
prepare workspace
        ↓
fetch/verify sources
        ↓
execute ordered build instructions
        ↓
run tests
        ↓
install/stage
        ↓
inspect result
        ↓
produce validation record
```

Execution semantics include:

- user / privilege
- working directory
- environment
- phase
- conditions
- expected result
- test expectations

The executor must know nothing about DocBook, book chapters, or presentation order.

Its result should include:

```text
validated filesystem installation
logs
test results
observed installed contents
metrics
```

## 6. Add LFS bootstrap as the special path

Once normal builds work, add the LFS-specific bootstrap path.

```text
                BUILD ENGINE

        bootstrap          normal
            │                │
            ▼                ▼
    bootstrap variants    final LFS
                          BLFS
```

Examples:

```text
binutils
    bootstrap-pass1
    bootstrap-pass2
    normal

gcc
    bootstrap-pass1
    bootstrap-pass2
    normal
```

Bootstrap orchestration owns:

- host validation
- `$LFS` environment
- cross compiler creation
- temporary tools
- filesystem transition
- chroot transition
- normal-build handoff

After the handoff, final LFS and BLFS use the same normal executor.

## 7. Replace jhalfs semantics with dev-layer execution

The first system-level proof is a complete LFS build from a release manifest without book parsing.

```text
release manifest
+
package definitions
+
bootstrap definitions
+
system procedures
        ↓
dev build executor
        ↓
complete LFS system
```

No publication XML may be an execution input.

This preserves the useful function of jhalfs while removing reverse-engineering of build semantics from the book.

## 8. Make validation first-class state

Each validation should record enough evidence to explain and reproduce acceptance:

```text
package/build identity
selected version
definition revision
source hashes
environment
architecture
commands executed
test result
expected failures
observed failures
installed contents
result status
```

Promotion flow:

```text
candidate
   ↓
package validation
   ↓
system validation
   ↓
accepted development version
```

The development manifest therefore means "latest accepted development state," not merely "latest version observed upstream."

## 9. Continuous discovery

Once candidate validation exists, introduce scheduled discovery.

```text
package-set manifest
       ↓
scheduler / manual trigger
       ↓
discover latest upstream version
       ↓
compare with development manifest
       ↓
new candidate?
       ↓
build/test/integrate
```

Discovery providers may include direct upstream sources, hosting-service releases/tags, and external release-monitoring services.

Discovery answers:

> What appears to be the newest acceptable upstream version?

Validation answers:

> Does that version work in the distro?

## 10. New-package reconciliation

Adding a package requires only adding it to the managed package-set manifest.

```text
package added to managed set
        ↓
scheduled or manual discovery
        ↓
definition missing?
        ↓
bootstrap candidate definition
        ↓
discover current version
        ↓
validate
```

Manual discovery simply expedites the same reconciliation process.

## 11. Failure and maintainer workflow

Failure is normal workflow, not an exceptional architecture path.

Example:

```text
foo 4.1 → 4.2 discovered
         ↓
build fails
         ↓
missing libbar
         ↓
maintainer notified
         ↓
libbar added to managed package set
         ↓
normal reconciliation continues
```

Maintainer actions may include:

- add dependency package
- blacklist/reject a version
- add/update patch
- update build definition
- adjust dependency relationships
- update test expectations
- change configuration
- defer a candidate

Developers modify authoritative intent or knowledge, never ad-hoc CI state.

## 12. Release manifests

A release is created by freezing validated development state.

```text
validated development manifest
        ↓
release decision
        ↓
freeze
        ↓
release manifest
```

Release identity consists of:

```text
package version set
+
definition repository revision/tag
+
selected profile(s)
```

The release manifest is immutable after publication.

## 13. Presentation compiler

Only after dev semantics are proven should publication generation become a primary implementation target.

Inputs:

```text
structural data
+
package/system data
+
editorial data
        ↓
presentation compiler
        ↓
standardized semantic document
```

Initially the standardized output should remain compatible with the existing DocBook/XSL rendering stack where practical.

```text
new source architecture
        ↓
new compiler
        ↓
canonical/compatible DocBook
        ↓
existing XSL
        ↓
same visible books
```

## 14. Split current LFS content by authority

Current LFS content naturally separates into:

- package/build data
- system procedures
- editorial/reference prose
- derived/aggregate pages
- hybrid pages containing both authoritative facts and prose

Package pages become:

```text
dev package/build data
+
editorial prose
+
presentation composition
```

System-procedure pages become:

```text
executable procedure data
+
editorial explanation
```

Derived pages such as package lists, patch lists, dependency views, release changes, and indexes should be generated from authoritative state rather than manually maintained.

## 15. Golden-book validation

The migration must continuously compare the new compiler against the existing publication.

Compare:

- hierarchy
- IDs
- page names
- section order
- prose
- commands
- tables
- cross references
- HTML output
- no-chunks HTML
- PDF output

The initial presentation milestone is successful when readers cannot distinguish the new backend from the existing publication.

## 16. Normalize BLFS into the same package universe

After LFS proves the model, migrate ordinary BLFS packages into the same normal package model.

Progressively add support for:

- required/recommended/optional/runtime dependencies
- kernel requirements
- configuration
- multiple sources
- patches
- conditional builds
- alternative builds

These are extensions of the common package model, not a separate BLFS engine.

## 17. Separate BLFS catalogs from executable collections

Presentation catalogs:

```text
Perl Modules
Python Modules
Xorg Input Drivers
```

These are document composition over independent packages.

Executable collections:

```text
Xorg Libraries
KDE Frameworks
KDE Plasma
```

These contain authoritative build semantics:

- membership
- order
- enablement
- shared build procedure
- per-member overrides

The KDE/Xorg cases are important stress tests because they expose exactly the sort of semantics that document-order inference cannot safely recover.

## 18. Profiles

After package and collection semantics stabilize, define profiles such as:

```text
lfs-base
xorg
plasma
gnome
lxqt
server
live
```

A profile selects:

```text
packages
collections
system procedures
defaults/policy
```

Both presentation and automation can resolve the same profile/state.

## 19. User automation

The user automation layer reuses the same resolver and validated build definitions.

```text
user selection/profile
        ↓
validated distro state
        ↓
dependency resolution
        ↓
ordered build plan
        ↓
generated build scripts
```

Generated build scripts are consumable artifacts, not recipe sources.

## 20. Packaging/deployment plugins

After a normal build produces a staged result, plugins handle user-specific packaging and deployment.

Possible plugins:

```text
direct install
tar package
Slackware txz
RPM-like package
pacman-like package
custom package manager
repository publisher
rootfs builder
image builder
live-media builder
```

Package definitions remain independent of the chosen package-management implementation.

## 21. Live/installable system outputs

Live media and installer creation become user/system realization outputs rather than independently encoded build knowledge.

```text
profile
+
validated packages
+
system procedures
        ↓
root filesystem
        ↓
initramfs
        ↓
bootloader
        ↓
SquashFS / image
        ↓
ISO / installer
```

## 22. Parallel migration period

Run old and new systems concurrently.

```text
CURRENT
XML → book
XML → jhalfs

NEW
normalized data → validation
normalized data + editorial + structure → book
```

The new path continuously proves equivalence before authority flips.

An intermediate compatibility state may generate legacy-compatible XML from the normalized model so existing renderers/tools remain usable while source authority moves.

## 23. Authority cutover

Two proofs are required before replacing the existing source-of-truth relationship.

### Build proof

```text
normalized model
→ complete LFS
→ representative BLFS profiles
```

with no semantic reconstruction from publication XML.

### Publication proof

```text
normalized model + editorial + structure
→ equivalent LFS/BLFS books
```

After both succeed, authored publication XML can cease being authoritative.

## 24. Remove reverse-engineering infrastructure

After cutover, remove:

- XML semantic extraction
- jhalfs book parsing
- dependency extraction hacks
- package-page parsing
- filename/order inference
- duplicate version-maintenance paths

The final architecture becomes strictly one-way:

```text
                    AUTHORITATIVE MODEL

package-set + package definitions + manifests
                + procedures/collections
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
        validation     books       automation
```

No rendered book feeds semantics back into the system.

## Implementation proof milestones

1. **Model proof** — represent 5–10 normal LFS packages losslessly.
2. **Execution proof** — build those packages from normalized definitions.
3. **Normal-LFS proof** — build all final LFS packages through one normal executor.
4. **Bootstrap proof** — build a complete LFS release without book parsing.
5. **Development proof** — scheduled discovery → candidate → test → promote/fail.
6. **Release proof** — freeze manifest → clean full release build.
7. **Presentation proof** — generate an equivalent LFS book from structure + package + editorial data.
8. **BLFS proof** — ordinary BLFS packages plus dependency/kernel/configuration semantics.
9. **Hard-BLFS proof** — KDE/Xorg collections and composite catalogs without document heuristics.
10. **User-system proof** — selected profile → generated scripts → packaging plugin → maintained/installable system.

## Recommended first implementation slice

Start with:

```text
prototype/
├── manifest
├── versions/
│   └── development
├── packages/
│   ├── zlib
│   ├── bash
│   ├── gzip
│   ├── make
│   └── coreutils
├── engine/
│   ├── resolve
│   ├── build
│   ├── test
│   └── inspect
└── results/
```

First prove:

```text
manifest
+
version manifest
+
version-independent definitions
        ↓
resolved packages
        ↓
build/test
        ↓
validated result
```

Then prove one successful version update:

```text
old development version
        ↓
discover new version
        ↓
candidate
        ↓
build/test
        ↓
promotion
```

Then deliberately prove failure handling:

```text
candidate fails
        ↓
development remains unchanged
        ↓
useful failure evidence
        ↓
maintainer changes authoritative definition/policy
        ↓
rerun
        ↓
promotion
```

This vertical slice proves the continuous-development architecture before the project invests heavily in publication migration, BLFS breadth, package-manager plugins, or user-facing automation.
