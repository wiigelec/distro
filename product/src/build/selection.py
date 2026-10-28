"""Strict manifest and ordered step selection for FS-001 (no recipe evaluation)."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re

class SelectionError(ValueError):
    pass

_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
_VERSION = re.compile(r"^[0-9][A-Za-z0-9.+_-]*$")
_DIGEST = re.compile(r"^[a-fA-F0-9]{64}$")


def _yaml(path: Path):
    try:
        import yaml
    except ImportError as e:
        raise SelectionError("PyYAML is required for YAML manifests/lists") from e
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise SelectionError(f"invalid YAML {path}: {e}") from e
    if not isinstance(data, dict):
        raise SelectionError(f"expected mapping in {path}")
    return data


def _keys(d: dict, required: set[str], optional: set[str] = frozenset()):
    if set(d) - required - optional or required - set(d):
        raise SelectionError(f"invalid fields (missing={required-set(d)}, unknown={set(d)-required-optional})")


def _name(s):
    return isinstance(s, str) and bool(_NAME.fullmatch(s))


def _version(s):
    return isinstance(s, str) and bool(_VERSION.fullmatch(s))


@dataclass(frozen=True)
class Source:
    url: str
    sha256: str


@dataclass(frozen=True)
class Manifest:
    name: str
    source: Source
    dependencies: tuple[str, ...]
    host_tools: tuple[str, ...]
    supplements: dict[str, Source]


@dataclass(frozen=True)
class Step:
    id: str
    name: str
    version: str
    recipe: Path


def _source(d):
    if not isinstance(d, dict):
        raise SelectionError("source must be a mapping")
    _keys(d, {"url", "sha256"})
    if not isinstance(d["url"], str) or not d["url"].startswith("https://") or "{" in d["url"].replace("{version}", "") or "}" in d["url"].replace("{version}", ""):
        raise SelectionError("source URL must be a single HTTPS template with optional {version}")
    if not isinstance(d["sha256"], str) or not _DIGEST.fullmatch(d["sha256"]):
        raise SelectionError("source requires literal SHA-256 digest")
    return Source(d["url"], d["sha256"].lower())


def load_manifests(directory: Path) -> dict[str, Manifest]:
    found = {}
    for path in sorted(directory.glob("*.yaml")):
        d = _yaml(path)
        _keys(d, {"name", "source", "dependencies"}, {"host_tools", "supplements"})
        name = d["name"]
        if not _name(name) or path.stem != name or name in found:
            raise SelectionError(f"manifest name/file mismatch or duplicate: {path}")
        deps = d["dependencies"]
        hosts = d.get("host_tools", [])
        supp = d.get("supplements", {})
        if not isinstance(deps, list) or not all(_name(v) for v in deps) or len(deps) != len(set(deps)) or name in deps:
            raise SelectionError(f"invalid dependencies: {name}")
        if not isinstance(hosts, list) or not all(_name(v) for v in hosts) or len(hosts) != len(set(hosts)):
            raise SelectionError(f"invalid host tools: {name}")
        if not isinstance(supp, dict) or not all(_name(k) for k in supp):
            raise SelectionError(f"invalid supplementary sources: {name}")
        found[name] = Manifest(name, _source(d["source"]), tuple(deps), tuple(hosts), {k: _source(v) for k,v in supp.items()})
    if not found:
        raise SelectionError("no package manifests")
    return found


def select_steps(list_file: Path, manifests: dict[str, Manifest], recipes_root: Path) -> tuple[Step, ...]:
    d = _yaml(list_file)
    _keys(d, {"steps"})
    if not isinstance(d["steps"], list) or not d["steps"]:
        raise SelectionError("steps must be a nonempty sequence")
    steps, ids, versions = [], set(), {}
    for position, item in enumerate(d["steps"]):
        if not isinstance(item, dict):
            raise SelectionError("step must be a mapping")
        _keys(item, {"name", "version", "recipe"}, {"id"})
        name, version, rel = item["name"], item["version"], item["recipe"]
        sid = item.get("id", f"{name}-{position+1}")
        if not _name(name) or name not in manifests or not _version(version) or not _name(sid):
            raise SelectionError("invalid step identity/version or unknown package")
        if sid in ids or (name in versions and versions[name] != version):
            raise SelectionError("duplicate step ID or conflicting package versions")
        if not isinstance(rel, str) or not rel.endswith(".sh"):
            raise SelectionError("recipe must be a relative Bash script")
        relative = Path(rel)
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] == ".":
            raise SelectionError("unsafe recipe path")
        recipe = (recipes_root / relative).resolve()
        if not recipe.is_relative_to(recipes_root.resolve()) or not recipe.is_file():
            raise SelectionError(f"recipe unavailable or outside recipe root: {rel}")
        for dependency in manifests[name].dependencies:
            if dependency not in versions:
                raise SelectionError(f"{name}: required prerequisite not selected earlier: {dependency}")
        ids.add(sid)
        versions[name] = version
        steps.append(Step(sid, name, version, recipe))
    return tuple(steps)
