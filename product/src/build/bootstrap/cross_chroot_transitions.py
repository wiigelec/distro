"""Evidence and fail-closed review for cross-chroot native-tool collisions.

No replacement is performed or authorized by this module. An exact inventory
and separately reviewed fingerprints are prerequisites to any later transition.
"""
from __future__ import annotations

from pathlib import Path

from build.bootstrap.cross_chroot_ownership import (
    OwnershipError, snapshot_imported_root,
)

Identity = tuple[str, int, str]


def native_collision_evidence(installed: Path, staged: Path) -> dict[str, tuple[Identity, Identity]]:
    """Report non-directory overlaps with prior and candidate identities.

    Shared directories are only acceptable when their modes match. A changed
    directory mode is a collision as well; directory collisions are never
    suitable for native ownership transitions.
    """
    installed_entries = snapshot_imported_root(installed)
    staged_entries = snapshot_imported_root(staged)
    if not staged_entries:
        raise OwnershipError("native staged installation is empty")
    return {
        name: (installed_entries[name], candidate)
        for name, candidate in sorted(staged_entries.items())
        if name in installed_entries
        and not (installed_entries[name][0] == candidate[0] == "dir"
                 and installed_entries[name][1] == candidate[1])
    }


def review_native_transitions(
    step_id: str,
    target: str,
    version: str,
    collisions: dict[str, tuple[Identity, Identity]],
    imported_baseline: dict[str, Identity],
    expected: dict[str, tuple[Identity, Identity]],
) -> tuple[str, ...]:
    """Verify every proposed transition against exact reviewed fingerprints.

    Native Binutils must not overwrite an existing entry. Only regular GCC
    compiler-private files from the original cross-toolchain import can ever
    qualify for *review*. This does not grant write permission to the caller.
    The expected map must be supplied by a separately approved, exact-path
    review of observed candidate files, never synthesized from collisions.
    """
    if step_id not in ("native-binutils", "native-gcc"):
        raise OwnershipError("native transition review requires a native step")
    if (not isinstance(target, str) or not target or "/" in target or
            not isinstance(version, str) or not version or "/" in version):
        raise OwnershipError("invalid native compiler identity")
    if not isinstance(collisions, dict) or not isinstance(expected, dict):
        raise OwnershipError("invalid native ownership evidence")
    if set(collisions) != set(expected):
        raise OwnershipError("native ownership transitions must enumerate every collision exactly")
    if step_id == "native-binutils" and collisions:
        raise OwnershipError("native Binutils may not replace imported or installed files")
    prefixes = (
        f"usr/lib/gcc/{target}/{version}/",
        f"usr/lib64/gcc/{target}/{version}/",
    )
    for name, pair in collisions.items():
        if (not isinstance(name, str) or name.startswith("/") or
                any(part in ("", ".", "..") for part in name.split("/"))):
            raise OwnershipError("invalid native collision path")
        if step_id != "native-gcc" or not name.startswith(prefixes):
            raise OwnershipError(f"unapproved native ownership path: {name}")
        prior, incoming = pair
        if (not isinstance(prior, tuple) or not isinstance(incoming, tuple) or
                len(prior) != 3 or len(incoming) != 3 or
                prior[0] != "file" or incoming[0] != "file"):
            raise OwnershipError(f"native transition must concern regular files: {name}")
        if imported_baseline.get(name) != prior:
            raise OwnershipError(f"native transition lacks matching imported ownership: {name}")
        if expected[name] != pair:
            raise OwnershipError(f"native transition fingerprints differ from reviewed evidence: {name}")
    return tuple(sorted(collisions))
