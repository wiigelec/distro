# LFS optimize prototype — milestone status

Last updated: 2026-10-05

Authoritative branch: `proto/lfs-optimize`

Roadmap:
`product/src/proto/docs/lfs-blfs-modernization-implementation-roadmap.md`

## Current milestone state

| Milestone | Status | Proof |
| --- | --- | --- |
| M1 — Model proof | COMPLETE | Version-independent normal-LFS package definitions plus development version manifest resolve successfully. |
| M2 — Execution proof | COMPLETE | Normal package executor builds, captures filesystem deltas, creates artifacts, realizes them, and verifies equivalence. |
| M3 — Normal-LFS proof | COMPLETE | All 80 final-system LFS packages execute through the same normal executor and can reconstruct a successful final filesystem. |
| M4 — Bootstrap proof | COMPLETE | Fresh Chapter 5–7 bootstrap hands directly to the normal executor; all 80 final-system packages build successfully without publication XML/book parsing. |
| M5 — Development proof | COMPLETE | Accepted state, candidate identity, validation, definition binding/drift rejection, review evidence, and guarded transactional promotion are implemented. |
| M6 — Release proof | SATISFIED BY COMPOSITION | M4 proves clean full-system realization from normalized state and M5 proves validated state identity and controlled promotion. Freezing accepted state under a release identity adds production plumbing but no unresolved prototype architecture question. |
| M7 — Presentation proof | IN PROGRESS — PACKAGE-PAGE MODEL PROVEN; CHAPTER 8 HIERARCHY SLICE ADDED | Zlib and Binutils prove package-page semantics. Chapter 8 structure now composes five presentation-only pages around the authoritative 80-package package-set order and derives numbering/local navigation, with a source-derived 13.1-systemd golden hierarchy fixture used only for drift detection. Whole-book composition and golden rendering remain open. |
| M8+ | NOT STARTED | BLFS, hard-BLFS, and user-system proofs remain later roadmap milestones. |

## M5 closure

The development proof demonstrates:

```text
accepted development
        ↓
discovery
        ↓
candidate
        ↓
validation
        ↓
promote / reject
```

Candidate identity binds the version manifest, package set, and package-definition
state. Validation rejects live definition drift. Plan-only validation cannot
promote. Test failures remain review evidence rather than being confused with
non-test build failure. Promotion stages accepted-state replacements and rolls
back already-replaced files after ordinary replacement failure.

These properties are sufficient to prove that continuous-development state can
sit above the normalized build model without changing build semantics.

## M6 disposition

M6 is intentionally not expanded into a separate prototype subsystem.

```text
validated accepted state       M5
        ↓
frozen state identity          naming/immutability boundary
        ↓
fresh bootstrap + full build   M4
```

Concrete release naming, retention, publication, and policy remain production
implementation work rather than an unresolved architecture risk.

## M7 package-page proof

The package-page presentation proof uses `zlib` and `binutils`:

```text
presentation/structure.json
        +
presentation/editorial/<package>.json
        +
resolve.py authoritative package/version result
        ↓
presentation.py
        ↓
DocBook-compatible semantic XML
```

The proof establishes these authority boundaries:

- presentation structure owns document identity, page hierarchy, and section composition;
- editorial data owns explanatory prose, admonitions, parameter explanations, and inline presentation semantics;
- normalized package/version state owns versions, sources, build metrics, procedures, command text/order, installed-content facts, dependencies, and installed-item classification;
- compiled XML is derived output.

Legacy `document` fields may remain in package definitions during migration, but
the presentation compiler does not consume them and validation no longer treats
them as package identity. This preserves roadmap invariant 8: document identity
is independent of package identity.

Zlib proves the simple linear instructional case. Binutils proves repeated
phases, stable command references, multiline commands, ordered editorial blocks,
admonitions, definition lists, inline filename/literal semantics, multiple
installed-content categories, and typed short descriptions.

## M7 Chapter 8 hierarchy slice

Chapter 8 provides a clean composition proof:

```text
presentation-owned chapter identity
+ 2 leading editorial pages
+ authoritative package-set order (80 packages)
+ presentation-owned package document identities
+ 3 trailing editorial pages
        ↓
85-page Chapter 8 hierarchy
        ↓
derived 8.1 ... 8.85 numbering
+ chapter-local previous/next navigation
```

The package order is not copied into presentation state. `package-set.json`
remains the sole order authority for the 80 normal final-system packages.
Presentation structure maps those package identities to document identities but
stores them as a mapping, not an ordered package list.

`presentation/golden/chapter08-hierarchy.json` is a migration/validation fixture
captured from LFS 13.1-systemd. It is not an input to compilation; the
presentation self-test uses it only to detect hierarchy, ID, or filename drift.

The hierarchy slice deliberately stops at Chapter 8 boundaries. Previous/next
links across chapter boundaries, book-level numbering, cross references,
indexes, aggregate pages, and rendered HTML/PDF equivalence remain subsequent
M7 work.

## Resume instruction

Run the prototype presentation validator directly after this slice lands:

```text
python3 product/src/proto/lfs_optimize/validate.py
```

If it passes, treat the Chapter 8 hierarchy model as proven and move next to
book-level composition: chapter ordering, cross-chapter navigation, and
cross-reference resolution before attempting full golden HTML/PDF comparison.
