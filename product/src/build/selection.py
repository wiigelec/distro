"""Strict manifest and ordered build-step selection (no recipe evaluation)."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
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
    verification: str
    # Legacy upstream sources remain unchanged. Repository-local sources have
    # no fabricated upstream URL and require separate immutable Git validation.
    kind: str = "upstream"
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class NativeCategories:
    build_tools: tuple[str, ...]
    build_link_dependencies: tuple[str, ...]
    runtime_dependencies: tuple[str, ...]


@dataclass(frozen=True)
class Manifest:
    name: str
    source: Source
    dependencies: tuple[str, ...]
    host_tools: tuple[str, ...]
    supplements: dict[str, Source]
    # FS-004 explicit categories; no implicit conversion of legacy dependencies.
    build_tools: tuple[str, ...] = ()
    build_link_dependencies: tuple[str, ...] = ()
    runtime_dependencies: tuple[str, ...] = ()
    native: NativeCategories | None = None


@dataclass(frozen=True)
class Step:
    id: str
    name: str
    version: str
    recipe: Path
    checksum: str
    supplements: dict[str, tuple[str, str]]


def _source(d):
    if not isinstance(d, dict):
        raise SelectionError("source must be a mapping")
    if d.get("kind") == "local":
        _keys(d, {"kind", "paths"})
        paths = d["paths"]
        if not isinstance(paths, list) or not paths or not all(
            isinstance(p, str) and p and not Path(p).is_absolute()
            and ".." not in Path(p).parts and Path(p).as_posix() == p
            and not p.startswith("./") for p in paths
        ) or len(set(paths)) != len(paths):
            raise SelectionError("invalid repository-local source paths")
        return Source("", "git-tree", "local", tuple(paths))
    _keys(d, {"url", "verification"})
    if not isinstance(d["url"], str) or not d["url"].startswith("https://") or "{" in d["url"].replace("{version}", "") or "}" in d["url"].replace("{version}", ""):
        raise SelectionError("source URL must be a single HTTPS template with optional {version}")
    if d["verification"] != "sha256":
        raise SelectionError("unsupported source verification scheme")
    return Source(d["url"], d["verification"])


def load_manifests(directory: Path) -> dict[str, Manifest]:
    found = {}
    for path in sorted(directory.glob("*.yaml")):
        d = _yaml(path)
        _keys(d, {"name", "source"}, {"dependencies", "host_tools", "supplements",
                                     "build_tools", "build_link_dependencies", "runtime_dependencies", "native"})
        name = d["name"]
        if not _name(name) or path.stem != name or name in found:
            raise SelectionError(f"manifest name/file mismatch or duplicate: {path}")
        deps = d.get("dependencies", [])
        categories = ("build_tools", "build_link_dependencies", "runtime_dependencies")
        categorized = {}
        for field in categories:
            values = d.get(field, [])
            if not isinstance(values, list) or not all(_name(v) for v in values) or len(set(values)) != len(values) or name in values:
                raise SelectionError(f"invalid {field}: {name}")
            categorized[field] = tuple(values)
        if "dependencies" in d and any(field in d for field in categories):
            raise SelectionError(f"legacy and categorized dependencies cannot be mixed: {name}")
        hosts = d.get("host_tools", [])
        supp = d.get("supplements", {})
        if not isinstance(deps, list) or not all(_name(v) for v in deps) or len(deps) != len(set(deps)) or name in deps:
            raise SelectionError(f"invalid dependencies: {name}")
        if not isinstance(hosts, list) or not all(_name(v) for v in hosts) or len(hosts) != len(set(hosts)):
            raise SelectionError(f"invalid host tools: {name}")
        if not isinstance(supp, dict) or not all(_name(k) for k in supp):
            raise SelectionError(f"invalid supplementary sources: {name}")
        native_raw = d.get("native")
        native_categories = None
        if native_raw is not None:
            if not isinstance(native_raw, dict):
                raise SelectionError(f"{name}: native categories must be a mapping")
            _keys(native_raw, {"build_tools", "build_link_dependencies", "runtime_dependencies"})
            checked = {}
            for field in ("build_tools", "build_link_dependencies", "runtime_dependencies"):
                values = native_raw[field]
                if (not isinstance(values, list) or not all(_name(value) for value in values)
                        or len(values) != len(set(values)) or name in values):
                    raise SelectionError(f"{name}: invalid native {field}")
                checked[field] = tuple(values)
            if any(field in d for field in categories):
                raise SelectionError(f"{name}: competing top-level and native categories")
            native_categories = NativeCategories(checked["build_tools"],
                                                checked["build_link_dependencies"],
                                                checked["runtime_dependencies"])
        found[name] = Manifest(name, _source(d["source"]), tuple(deps), tuple(hosts),
                               {k: _source(v) for k,v in supp.items()},
                               categorized["build_tools"], categorized["build_link_dependencies"],
                               categorized["runtime_dependencies"], native_categories)
    if not found:
        raise SelectionError("no package manifests")
    return found


def select_steps(list_file: Path, manifests: dict[str, Manifest], recipes_root: Path,
                 *, imported: Mapping[str, str] | None = None) -> tuple[Step, ...]:
    """Resolve manifest dependencies against prior steps or verified imported capabilities.

    `imported` must come from a validated Stage 1A handoff and filesystem check,
    not a stage list. Without it, Stage 1A's existing selection is unchanged.
    """
    if imported is None:
        imported = {}
    if not isinstance(imported, Mapping):
        raise SelectionError("imported prerequisites must be a package/version mapping")
    for name, version in imported.items():
        if not _name(name) or name not in manifests or not _version(version):
            raise SelectionError("invalid imported prerequisite identity/version")
    d = _yaml(list_file)
    _keys(d, {"steps"})
    if not isinstance(d["steps"], list) or not d["steps"]:
        raise SelectionError("steps must be a nonempty sequence")
    steps, ids, versions = [], set(), {}
    for position, item in enumerate(d["steps"]):
        if not isinstance(item, dict):
            raise SelectionError("step must be a mapping")
        _keys(item, {"name", "version", "recipe", "checksum"}, {"id", "supplements"})
        name, version, rel = item["name"], item["version"], item["recipe"]
        sid = item.get("id", f"{name}-{position+1}")
        if not _name(name) or name not in manifests or not _version(version) or not _name(sid):
            raise SelectionError("invalid step identity/version or unknown package")
        if manifests[name].source.kind != "upstream":
            raise SelectionError("legacy ordered selector cannot consume repository-local sources")
        checksum = item["checksum"]
        if not isinstance(checksum, str) or not _DIGEST.fullmatch(checksum):
            raise SelectionError("invalid selected source checksum")
        raw_supp = item.get("supplements", {})
        if not isinstance(raw_supp, dict) or set(raw_supp) - set(manifests[name].supplements):
            raise SelectionError("unknown supplementary selection")
        supplements = {}
        for identity, selected in raw_supp.items():
            if not isinstance(selected, dict):
                raise SelectionError("invalid supplementary selection")
            _keys(selected, {"version", "checksum"})
            if not _version(selected["version"]) or not isinstance(selected["checksum"], str) or not _DIGEST.fullmatch(selected["checksum"]):
                raise SelectionError("invalid supplementary version/checksum")
            supplements[identity] = (selected["version"], selected["checksum"].lower())
        if sid == "gcc-pass1" and set(supplements) != {"gmp", "mpfr", "mpc"}:
            raise SelectionError("GCC pass 1 requires pinned GMP/MPFR/MPC")
        if sid in ids or (name in versions and versions[name] != version):
            raise SelectionError("duplicate step ID or conflicting package versions")
        if name in imported and imported[name] != version:
            raise SelectionError(f"{name}: selected version conflicts with imported prerequisite")
        if not isinstance(rel, str) or not rel.endswith(".sh"):
            raise SelectionError("recipe must be a relative Bash script")
        relative = Path(rel)
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] == ".":
            raise SelectionError("unsafe recipe path")
        recipe = (recipes_root / relative).resolve()
        if not recipe.is_relative_to(recipes_root.resolve()) or not recipe.is_file():
            raise SelectionError(f"recipe unavailable or outside recipe root: {rel}")
        for dependency in manifests[name].dependencies:
            if dependency not in versions and dependency not in imported:
                raise SelectionError(f"{name}: required prerequisite not selected earlier or verified in Stage 1A: {dependency}")
        ids.add(sid)
        versions[name] = version
        steps.append(Step(sid, name, version, recipe, checksum.lower(), supplements))
    return tuple(steps)
