"""FS-004 verified, Stage 1C-only filesystem recipe selection.

This is not the generic native package runner or a Manage package installation.
It requires a selected committed revision and does not execute the recipe.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from build.selection import SelectionError, Manifest, load_manifests
from build.local_provenance import verify_local_source

_STAGE = Path(__file__).resolve().parent / 'bootstrap/distro-buildroot'
_MANIFESTS = Path(__file__).resolve().parent / 'packages'
_RECIPE = _STAGE / 'recipes/filesystem.sh'

@dataclass(frozen=True)
class FilesystemSelection:
    name: str
    version: str
    recipe: Path
    source_digests: dict[str, str]
    manifest: Manifest


def select_filesystem(root: Path, revision: str) -> FilesystemSelection:
    """Verify the immutable local definition and recipe before Build consumes either."""
    manifests = load_manifests(_MANIFESTS)
    if 'filesystem' not in manifests:
        raise SelectionError('missing authoritative filesystem manifest')
    manifest = manifests['filesystem']
    if manifest.dependencies or manifest.build_tools or manifest.build_link_dependencies or manifest.runtime_dependencies:
        raise SelectionError('filesystem must have no package dependencies')
    selected = manifest.source.paths
    expected = ('product/src/build/packages/filesystem.yaml', 'product/src/build/bootstrap/distro-buildroot/recipes/filesystem.sh')
    if selected != expected:
        raise SelectionError('filesystem source paths differ from reviewed definition')
    if not _RECIPE.is_file() or _RECIPE.is_symlink():
        raise SelectionError('filesystem recipe is unavailable')
    digests = verify_local_source(manifest.source, root, revision)
    return FilesystemSelection('filesystem', '1', _RECIPE, digests, manifest)
