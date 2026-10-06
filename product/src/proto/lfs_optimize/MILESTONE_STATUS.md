# LFS optimize prototype — milestone status

Last updated: 2026-10-06

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
| M7 — Presentation proof | COMPLETE — 199/199 CHUNKS COMPLETE; 0 AUTHORITY GAPS | All 80/80 Chapter 8 package pages and all 119/119 non-package bodies render from normalized authority plus presentation-owned editorial state. All 38 referenced nested targets are physically present in rendered HTML. |
| M8 — BLFS proof | IN PROGRESS | PAM/Shadow/systemd semantics are modeled; a QEMU direct-kernel boot harness now bridges the M4 filesystem result to the booted-LFS environment required for real BLFS execution. Boot execution is still required before BLFS build claims. |
| M9+ | NOT STARTED | Hard-BLFS collections/catalogs and user-system proofs remain later roadmap milestones. |

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

## M7 book graph slice

The book graph extends presentation composition above Chapter 8:

```text
presentation-owned frontmatter
+ presentation-owned part/chapter/appendix hierarchy
+ Chapter 8 authoritative package-set composition
        ↓
199 chunked documents
        ↓
global previous/next navigation
+ graph-level xref target index
```

Part landing pages participate in navigation. For example, the Chapter 7 to
Chapter 8 transition is:

```text
last Chapter 7 page
        ↓
Part IV landing page
        ↓
Chapter 8 landing page
        ↓
8.1 Introduction
```

`presentation/golden/book-hierarchy.json` is captured from the uploaded LFS
13.1-systemd source and is validation-only. Runtime composition reads only
presentation structure plus authoritative distro state.

This slice resolves xrefs to graph-level chunk targets: part, chapter/appendix,
and top-level page IDs. Nested anchors inside page bodies are intentionally not
promoted into the graph yet; they belong with the subsequent editorial-content
and rendered-output proof.

## M7 nested xref slice

The source inventory contains 161 internal references to 86 distinct targets.
Forty-eight targets are already chunk-level book-graph documents. The remaining
38 are intra-document targets:

```text
33 sect2
 1 sect3
 1 bridgehead
 1 listitem
 1 explicit anchor
 1 unchunked sect1
```

Presentation structure owns the binding from each nested target ID to its
containing chunk document. Runtime xref resolution therefore requires only:

```text
presentation structure
        +
composed book graph
        ↓
target ID
        ↓
chunk filename + target fragment
```

`presentation/golden/xref-targets.json` records the LFS 13.1-systemd reference
inventory for validation only. It is not used by runtime composition.

This slice deliberately models only anchors that are actually referenced by the
source book. Other incidental IDs remain renderer details until a semantic need
for them is demonstrated.

## M7 chunked HTML package slice

The first rendered-output proof covers the two package pages already used for
semantic composition: Zlib and Binutils.

The renderer consumes the semantic package model plus the composed book graph:

```text
normalized package/version state
+ presentation editorial/structure
+ composed book graph
        ↓
semantic package XML
        ↓
chunked HTML package page
```

The golden comparison is semantic, not byte-for-byte. It validates:

- chunk filename and page ID;
- reader-visible section numbering and headings;
- previous/next/up/home navigation destinations;
- authoritative command text and order;
- build-time and disk-space metrics;
- contents fragment identity; and
- installed-summary labels and reader-visible list punctuation.

Stylesheet classes, CSS, whitespace, and incidental serialization are explicitly
not authority.

This slice also closes a small reader-visible gap in installed summaries: lists
of three or more entries now use the same natural-language final `and` form as
the reference book rather than a raw comma join.

`presentation/golden/chunked-html-packages.json` is a validation oracle only.
Runtime rendering does not consume it.

## M7 full chunk-routing slice

The two-package HTML proof exposed a full-book requirement that local filenames
alone cannot represent: many chunks share names such as `introduction.html`.

Presentation document identity now includes a route directory at the unit level.
Pages inherit that route, producing collision-free paths such as:

```text
prologue/preface.html
chapter02/introduction.html
chapter08/zlib.html
chapter09/introduction.html
appendices/licenses.html
```

The composed book derives:

- all 199 output paths;
- hierarchy-owned `up` targets;
- relative previous/next/up/home links;
- relative cross-chunk xref hrefs; and
- nested fragment hrefs.

The source-derived `presentation/golden/chunked-html-book.json` validates route,
title, and navigation identity only. Runtime rendering never consumes it.

Zlib and Binutils retain their fully modeled package bodies. Documents whose
editorial bodies have not yet been migrated render as explicit structural shells
with `data-body-status="pending-editorial-migration"`. No prose or commands are
fabricated to fill those gaps.

The CLI can materialize the complete browser-navigable chunk tree:

```text
python3 product/src/proto/lfs_optimize/presentation.py   --html-book-dir /tmp/lfs-html
```

## M7 generic editorial-body slice

Four representative pages now exercise a generic document-body model:

- Preface / Foreword (`pre-foreword`);
- Host System Requirements (`ch-partitioning-hostreqs`);
- Binutils Pass 1 (`ch-tools-binutils-pass1`); and
- Chapter 8 Introduction (`ch-system-introduction`).

The runtime authority split is:

```text
presentation/editorial-documents/<document-id>.json
        → prose, lists, sections, admonitions, links/xrefs
bootstrap-13.1.json
        → bootstrap command text/order
presentation book graph
        → chunk routes and xref hrefs
```

Bootstrap editorial blocks bind commands by index and never duplicate command
strings. Generic xrefs bind only target identity and display text; their hrefs are
resolved from the composed chunk graph.

The generic block vocabulary is intentionally limited to constructs demonstrated
by this slice: paragraph/rich inline content, preformatted text, ordered/unordered
lists, nested sections/headings, admonitions, definition lists, segmented lists,
external links, and internal xrefs.

`presentation/golden/editorial-slice.json` is source-derived validation state
only. Runtime rendering does not consume it.

## M7 editorial vocabulary completion slice

The first generic editorial slice exposed one semantic extraction bug: block
content nested inside a DocBook paragraph could be flattened into plain inline
text. Host System Requirements demonstrates this with a warning paragraph that
contains an itemized list.

The model now represents mixed flow explicitly and adds the remaining constructs
demonstrated by non-normal-package source pages:

- semantic tables;
- blockquotes;
- footnotes;
- keyboard keys/combinations;
- superscripts; and
- code-like inline forms such as computer output, functions, constants, prompts,
  and tokens.

The proof pages added by this slice are:

```text
ch-tools-toolchaintechnotes
ch-tools-glibc
ch-system-pkgmgt
afterlfs
```

`ch-tools-glibc` binds all 16 executable commands to `bootstrap-13.1.json`;
publication editorial state does not duplicate those recipes.

## M7 complete non-package editorial migration

The non-package chunk set is now fully modeled:

```text
119 non-package chunks
└── 119 complete presentation bodies
    ├── narrative/editorial pages
    ├── 30 bootstrap package stages bound to bootstrap-13.1.json
    └── operational pages bound to normalized bootstrap/system-operation authority
```

The final operational migration covers all 30 formerly deferred pages. Across
those pages, the LFS source contains 120 `screen/userinput` command screens.
Eleven already had normalized authority in the existing `chroot_setup` and
`cleanup` sequences in `bootstrap-13.1.json`; those commands are referenced
directly rather than duplicated. The remaining 109 commands are owned by
`system-operations-13.1.json`.

System-operation state distinguishes procedure, template, check, interactive,
session-transition, and illustrative command semantics. Presentation JSON stores
only authority references and editorial structure; it does not duplicate
command strings.

`presentation/golden/editorial-bulk.json` records source-derived semantic
digests, xref targets, and canonical command hashes for validation only.
Runtime rendering consumes normalized authority, never the golden.

## M7 bulk normalized package rendering

The Chapter 8 package inventory is now fully normalized for presentation:

```text
80 normal package pages
└── 80 source ↔ normalized command mappings proven
```

All 80 package pages render from normalized package/version state plus
presentation-owned editorial overlays. Executable command text always comes
from normalized package state. The source-derived golden stores only SHA-256
values for command equivalence; source command strings are not runtime inputs.

The ten formerly deferred package pages are now closed:

```text
glibc
gmp
libxcrypt
ncurses
coreutils
groff
grub
make
texinfo
util-linux
```

Their closure proves the extra semantics required beyond simple one-screen to
one-command mapping: illustrative commands, supplemental procedures, command
grouping, publication-only source forms, normalized build parameters, alternate
procedures, and strict source-command equivalence.

Groff proves normalized parameter authority with validated `paper_size`
defaults/overrides. GRUB proves that platform-specific EFI rebuild cycles can
remain explicit supplemental procedures while the LFS BIOS path stays the
default publication/execution path. Glibc proves a larger mixed case: the
default minimum locale set, the all-locales alternative, upgrade-only
supplemental procedures, complete installed summaries, and the full source
short-description inventory.

Resolver substitution is intentionally shell-safe. Only known
`{identifier}` placeholders are substituted; doubled braces preserve legacy
literal-brace escapes, and other shell brace syntax passes through unchanged.
Validation pins these behaviors with Groff, Binutils, Pkgconf, and Glibc cases.

Installed-summary labels are exact presentation semantics rather than inferred
from item count. This preserves source wording even where cardinality and labels
do not line up mechanically.

Together with the 119 complete non-package chunks, all 199/199 chunk bodies are
now complete.

## M7 closure

M7 is complete. The presentation proof now demonstrates, across the whole LFS
13.1-systemd book:

- all 80 normal package pages render from normalized package/version authority;
- all 119 non-package pages render from presentation-owned editorial structure
  with executable command text bound to normalized bootstrap or system-operation
  authority;
- all 199 chunk routes and navigation relationships are derived from the book
  graph;
- all 161 source xrefs resolve, including all 38 referenced nested targets; and
- every referenced nested target is physically present as an `id` in its
  rendered target chunk.

The final nested-target closure preserves bridgehead, list-item, unchunked
section, package-content, and explicit-anchor identities needed by the source
reference graph.

## Resume instruction

Run:

```text
python3 product/src/proto/lfs_optimize/validate.py
```

Direct validation should pass with M7 treated as complete. The next roadmap work
is M8 — BLFS.

## M8 first slice — Linux-PAM + systemd

The first BLFS proof deliberately targets a cross-package integration transition.
`blfs-package-set.json` selects `linux-pam`, then the named `shadow[blfs-pam]`
rebuild/configuration, then `systemd[blfs-pam]`. Package identity remains
independent from Build identity; named builds live under `blfs-builds/`.

Linux-PAM introduces the first explicit BLFS kernel requirement (`CONFIG_AUDIT`)
and required post-install rebuild/reconfiguration edges. Shadow now exercises
the authentication-critical configuration transition: BLFS PAM service files,
`login.defs` handoff, access/limits handoff, and an explicit manual login check
that is recorded as review evidence rather than executed inside the disposable
chroot. The systemd build then enables PAM, installs its PAM configuration, and
records `systemctl daemon-reexec` as a session transition.

## M8 booted-LFS prerequisite

BLFS execution must be proven on a booted LFS system, not only against a cloned
filesystem/chroot. The prototype therefore adds a boot harness between the M4
filesystem result and BLFS execution:

```text
M4 completed LFS filesystem
        ↓
LFS 7.1.8 kernel built inside that filesystem
        ↓
QEMU virtio ext4 root
        ↓
systemd PID 1 → multi-user.target
        ↓
DISTRO_BOOT_PROOF_OK on ttyS0
        ↓
booted environment eligible for BLFS execution
```

The harness uses QEMU direct-kernel boot intentionally. GRUB remains represented
by normalized Chapter 10 system operations, but bootloader deployment is not
required to answer the M8 prerequisite: whether the normalized LFS result can
run as a real system with its own kernel and systemd PID 1.

The boot kernel forces the QEMU root/console drivers built-in and also enables
`CONFIG_AUDIT=y`, satisfying the kernel requirement already modeled by the
Linux-PAM/systemd BLFS slice. `validate_boot.py` validates the plan without
requiring root or QEMU. `boot.py` performs the actual proof and writes
`boot/result.json` plus the QEMU serial log.

M8 must not claim real BLFS package execution until this boot proof succeeds.
