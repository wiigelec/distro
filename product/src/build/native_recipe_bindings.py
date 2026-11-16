"""FS-004 Stage 1C native recipe inventory; no package execution or publication.

This binds the pinned catalog to shared authoritative source manifests and
new target-native recipe paths. It cannot infer or authorize relationships.
Until every legacy manifest is explicitly classified and closure is resolved,
calling this selector is never evidence of a runnable native package set.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
from build.selection import Source, SelectionError, load_manifests
from build.native_catalog import load_native_catalog
from build.local_provenance import verify_local_source

STAGE = Path(__file__).resolve().parent / 'bootstrap/distro-buildroot'
PACKAGES = Path(__file__).resolve().parent / 'packages'
CATALOG = STAGE / 'lists/native-sources.yaml'

@dataclass(frozen=True)
class NativeRecipeBinding:
    name: str
    version: str
    checksum: str | None
    recipe: Path
    recipe_sha256: str


def inspect_native_recipe_bindings(*, stage: Path = STAGE,
                                   packages: Path = PACKAGES) -> tuple[NativeRecipeBinding, ...]:
    """Resolve exact static bindings; this cannot launch the Build controller."""
    stage, packages = Path(stage), Path(packages)
    selected = load_native_catalog(stage / 'lists/native-sources.yaml')
    manifests = load_manifests(packages)
    bindings = []
    for item in selected:
        manifest = manifests.get(item.name)
        if manifest is None or manifest.name != item.name or manifest.source.kind != item.kind:
            raise SelectionError(f'{item.name}: source manifest/category mismatch')
        if item.kind == 'upstream':
            if manifest.source.verification != 'sha256' or not manifest.source.url:
                raise SelectionError(f'{item.name}: missing verified upstream source')
        elif not manifest.source.paths or manifest.source.verification != 'git-tree':
            raise SelectionError(f'{item.name}: missing immutable local source')
        recipe = stage / 'recipes' / (item.name + '.sh')
        if recipe.is_symlink() or not recipe.is_file() or recipe.resolve() != recipe.absolute():
            raise SelectionError(f'{item.name}: missing/unsafe native recipe')
        data = recipe.read_bytes()
        if not data.startswith(b'#!/usr/bin/env bash\n') or b'\x00' in data:
            raise SelectionError(f'{item.name}: invalid native Bash recipe source')
        bindings.append(NativeRecipeBinding(item.name, item.version, item.checksum,
                                            recipe, hashlib.sha256(data).hexdigest()))
    if len(bindings) != 13 or len({b.name for b in bindings}) != 13:
        raise SelectionError('native recipe inventory incomplete')
    return tuple(bindings)


def verify_native_recipe_revision(root: Path, revision: str) -> tuple[NativeRecipeBinding, ...]:
    """Verify recipe bytes in immutable Git revision; never execute recipes."""
    bindings = inspect_native_recipe_bindings()
    root = Path(root)
    relative = []
    for binding in bindings:
        try:
            rel = binding.recipe.relative_to(root).as_posix()
        except ValueError as exc:
            raise SelectionError('native recipe is outside repository') from exc
        relative.append(rel)
    evidence = verify_local_source(Source('', 'git-tree', 'local', tuple(relative)), root, revision)
    for binding, rel in zip(bindings, relative):
        if evidence[rel] != binding.recipe_sha256:
            raise SelectionError('native recipe content digest mismatch')
    return bindings
