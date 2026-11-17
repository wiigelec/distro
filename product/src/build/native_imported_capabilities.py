"""FS-004 authentication of Stage 1B bootstrap construction capabilities.

The already-validated cross-chroot handoff is the authority, not caller-declared
package versions. This is a bootstrap provider gate, never installed closure.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import stat

from build.bootstrap.cross_chroot_handoff import validate_cross_chroot_handoff
from build.native_package_execution import STAGE1B, plan_native_package_steps
from build.selection import SelectionError, _yaml

# Selected tool names, not an invented package version catalog. These tools
# are present in the Stage 1B handoff and are necessary to break bootstrap
# construction cycles without inserting edges into the installed graph.
_REQUIRED_TOOLS = {
    'gcc': ('gcc', 'g++'),
    'make': ('make',),
    'bash': ('bash',),
    'binutils': ('as', 'ld'),
}

# FS-002 Issue #15: compatibility with the separately verified Findutils
# addition to the Stage 1B handoff. This is not a floating source allowance:
# only the exact reviewed FS-002 source pin is supported before branch
# integration. Keep the historical Stage 1B pins authoritative for all other
# packages, and require both new native executables in the restored root.
_REVIEWED_STAGE1B_ADDITIONS = {
    'findutils': ('4.10.0',
                  '1387e0b67ff247d2abde998f90dfbf70c1491391a59ddfecb8ae698789f0a4f5',
                  ('find', 'xargs')),
}


@dataclass(frozen=True)
class VerifiedStage1BProvider:
    archive_sha256: str
    capabilities: tuple[tuple[str, str], ...]
    root: Path


def _pinned_stage1b(path: Path) -> dict[str, tuple[str, str]]:
    """Resolve the exact accepted Stage 1B selections; reject ambiguity."""
    data = _yaml(path)
    steps = data.get('steps')
    if not isinstance(steps, list) or not steps:
        raise SelectionError('Stage 1B source selection is missing')
    selected = {}
    for entry in steps:
        if not isinstance(entry, dict):
            raise SelectionError('invalid Stage 1B source entry')
        name, version, checksum = (entry.get(k) for k in ('name','version','checksum'))
        if not all(isinstance(x,str) and x for x in (name,version,checksum)):
            raise SelectionError('invalid Stage 1B source identity')
        if name in selected:
            raise SelectionError('ambiguous Stage 1B source identity')
        selected[name] = (version,checksum.lower())
    return selected


def _executable_in_root(root: Path, program: str) -> None:
    """Never trust executable paths which resolve to the host outside root."""
    location = root / 'usr/bin' / program
    try:
        resolved = location.resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError as exc:
        raise SelectionError(f'Stage 1B executable absent: {program}') from exc
    if not resolved.is_relative_to(root) or not stat.S_ISREG(mode) or not mode & 0o111:
        raise SelectionError(f'Stage 1B executable unsafe or not executable: {program}')


def authenticate_stage1b_provider(archive: Path, restored_root: Path, *,
                                  selection_file: Path = STAGE1B) -> VerifiedStage1BProvider:
    """Revalidate archive and provenance, then gate on restored tool binaries.

    The caller must first restore the handoff through restore_cross_chroot;
    authenticated capabilities never authorize writing to the imported root.
    """
    archive = Path(archive).absolute()
    root = Path(restored_root).absolute()
    if (root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root
            or archive.is_relative_to(root)):
        raise SelectionError('invalid Stage 1B imported root or archive location')
    from build.bootstrap.cross_chroot_handoff import METADATA_NAME, ARCHIVE_NAME
    if archive.name != ARCHIVE_NAME or archive.is_symlink() or not archive.is_file():
        raise SelectionError('Stage 1B archive identity mismatch')
    marker = archive.parent / METADATA_NAME
    if marker.is_symlink() or not marker.is_file():
        raise SelectionError('Stage 1B completion metadata missing')
    import json
    try:
        metadata = json.loads(marker.read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:
        raise SelectionError('Stage 1B metadata invalid') from exc
    validate_cross_chroot_handoff(archive,metadata)
    accepted = _pinned_stage1b(selection_file)
    declared = {}
    for item in metadata['sources']:
        name = item['package']
        if name in declared or (name not in accepted and
                                name not in _REVIEWED_STAGE1B_ADDITIONS):
            raise SelectionError('ambiguous or unsupported Stage 1B source')
        declared[name] = (item['version'],item['sha256'])
    expected = dict(accepted)
    for name, (version, checksum, programs) in _REVIEWED_STAGE1B_ADDITIONS.items():
        # Only the explicitly pinned FS-002 addition is permitted. Neither an
        # arbitrary source nor an unknown Findutils version may be accepted.
        if name in declared:
            expected[name] = (version, checksum)
            for program in programs:
                _executable_in_root(root, program)
    if declared != expected:
        raise SelectionError('Stage 1B handoff differs from selected source pins')
    for name, programs in _REQUIRED_TOOLS.items():
        if name not in declared:
            raise SelectionError('missing selected Stage 1B tool capability: ' + name)
        for program in programs:
            _executable_in_root(root,program)
    # The existing handoff verifier already checks archive bytes, size and ELF
    # evidence. This digest is a traceable identity, not an installed relation.
    return VerifiedStage1BProvider(metadata['artifact']['sha256'],
                                  tuple(sorted((n, declared[n][0]) for n in _REQUIRED_TOOLS)),root)


def plan_native_packages_from_handoff(repository: Path, revision: str, *,
                                      archive: Path, restored_root: Path):
    """Tie the existing planner to an authenticated bootstrap provider."""
    evidence = authenticate_stage1b_provider(archive,restored_root)
    return evidence, plan_native_package_steps(repository,revision,
                           verified_imported=dict(evidence.capabilities))
