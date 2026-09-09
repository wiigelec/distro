#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "repo" / "design"
PLANNING_ROOT = ROOT / "repo" / "planning"
SPECS_ROOT = ROOT / "repo" / "specs"
MANIFEST = ROOT / "repo" / "validation" / "requirement-evaluation.json"
FRAMEWORK_SOURCE_RECORD = ROOT / "repo" / "validation" / "framework-source.json"
STRUCTURE_POLICY = ROOT / "repo" / "validation" / "structure-policy.json"
ENTRYPOINT = ROOT / "repo" / "scripts" / "validate"
ROOT_ENTRYPOINT = ROOT / "scripts" / "validate"
PRODUCT_ROOT = ROOT / "product"
PRODUCT_SPECS_ROOT = PRODUCT_ROOT / "specs"
PRODUCT_ENTRYPOINT = PRODUCT_ROOT / "scripts" / "validate"
PRODUCT_VALIDATION_ROOT = PRODUCT_ROOT / "validation"
PRODUCT_MANIFEST = PRODUCT_VALIDATION_ROOT / "requirement-evaluation.json"
PRODUCT_VALIDATOR = PRODUCT_VALIDATION_ROOT / "validate_product.py"
CANONICAL_PRODUCT_ENTRYPOINT = """#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$repo_root/product/validation/validate_product.py" "$@"
"""
README = ROOT / "README.md"
AGENTS = ROOT / "AGENTS.md"
OLD_WORKFLOW = ROOT / ".github" / "workflows" / "fs0-conformance.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "validation.yml"

TASKS = (
    "design-corpus",
    "repository-structure",
    "planning-structure",
    "manifest-integrity",
    "validation-entrypoint",
    "docs-alignment",
    "ci-delegation",
    "validation-gate",
    "framework-regression",
)

FS_BASENAME_RE = re.compile(r"^(FS-\d{3})-(.+)$")
REQ_HEADING_RE = re.compile(r"^### (FS-\d{3}-NR-\d{3}) — .+$", re.MULTILINE)
ALL_H3_RE = re.compile(r"^### (.+)$", re.MULTILINE)

# FS-001 has an explicit mechanical requirement naming the exact Design revision.
FS001_DESIGN_REVISION = "36735bd44e47b70f97221d61033e2affca9b9616"


def fail(message: str) -> None:
    raise AssertionError(message)


def read(path: Path) -> str:
    if not path.is_file():
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            rel = path
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


def git_commit_exists(revision: str) -> bool:
    cp = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return cp.returncode == 0


def discover_functional_sets(
    planning_root: Path = PLANNING_ROOT,
    specs_root: Path = SPECS_ROOT,
) -> list[tuple[str, str, Path, Path]]:
    planning: dict[str, tuple[str, Path]] = {}
    specs: dict[str, tuple[str, Path]] = {}

    if not planning_root.is_dir():
        fail("repo/planning must exist")
    if not specs_root.is_dir():
        fail("repo/specs must exist")

    for path in planning_root.iterdir():
        if not path.is_dir() or not path.name.startswith("FS-"):
            continue
        match = FS_BASENAME_RE.fullmatch(path.name)
        if not match:
            fail(f"invalid Functional Set Planning directory name: {path.name}")
        fs_id = match.group(1)
        if fs_id in planning:
            fail(f"duplicate Functional Set Planning identity: {fs_id}")
        planning[fs_id] = (path.name, path)

    for path in specs_root.iterdir():
        if not path.is_file() or path.suffix != ".md" or not path.name.startswith("FS-"):
            continue
        match = FS_BASENAME_RE.fullmatch(path.stem)
        if not match:
            fail(f"invalid Functional Set specification name: {path.name}")
        fs_id = match.group(1)
        if fs_id in specs:
            fail(f"duplicate Functional Set specification identity: {fs_id}")
        specs[fs_id] = (path.stem, path)

    if set(planning) != set(specs):
        fail(
            "Functional Set Planning/specification correspondence mismatch; "
            f"planning_only={sorted(set(planning)-set(specs))}, "
            f"spec_only={sorted(set(specs)-set(planning))}"
        )

    result = []
    for fs_id in sorted(planning):
        planning_name, planning_dir = planning[fs_id]
        spec_name, spec_path = specs[fs_id]
        if planning_name != spec_name:
            fail(
                f"Functional Set Planning/specification basename mismatch for {fs_id}: "
                f"{planning_name} != {spec_name}"
            )
        result.append((fs_id, planning_name, planning_dir, spec_path))
    return result


def parse_specification(spec_path: Path, fs_id: str) -> tuple[dict[str, str], set[str]]:
    text = read(spec_path)
    title = re.search(r"^# (FS-\d{3})\b", text, flags=re.MULTILINE)
    if not title or title.group(1) != fs_id:
        fail(f"{spec_path.name} specification identity does not match {fs_id}")

    all_h3 = ALL_H3_RE.findall(text)
    headings = list(REQ_HEADING_RE.finditer(text))
    if len(all_h3) != len(headings):
        malformed = [
            heading
            for heading in all_h3
            if not re.fullmatch(r"FS-\d{3}-NR-\d{3} — .+", heading)
        ]
        fail(f"{spec_path.name} contains malformed normative requirement heading: {malformed}")

    requirements: dict[str, str] = {}
    inactive: set[str] = set()

    for index, heading_match in enumerate(headings):
        req = heading_match.group(1)
        if not req.startswith(fs_id + "-NR-"):
            fail(f"{spec_path.name} requirement identity does not match owning Functional Set: {req}")
        if req in requirements:
            fail(f"duplicate normative requirement identity: {req}")

        block_end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        block = text[heading_match.end():block_end]

        classifications = re.findall(
            r"^\*\*Classification: ([^*\n]+)\*\*$",
            block,
            flags=re.MULTILINE,
        )
        if len(classifications) != 1 or classifications[0] not in {"M", "S", "B"}:
            fail(
                f"{spec_path.name} requirement {req} must contain exactly one "
                "Classification of M, S, or B"
            )

        states = re.findall(
            r"^\*\*State: ([^*\n]+)\*\*$",
            block,
            flags=re.MULTILINE,
        )
        if len(states) > 1:
            fail(f"{spec_path.name} requirement {req} contains duplicate State markers")
        if states and states[0] != "Inactive":
            fail(
                f"{spec_path.name} requirement {req} State must be Inactive "
                "when explicitly present"
            )

        requirements[req] = classifications[0]
        if states:
            inactive.add(req)

    if not requirements:
        fail(f"{spec_path.name} contains no normative requirements")
    return requirements, inactive

def validate_functional_set(
    fs_id: str,
    planning_dir: Path,
    spec_path: Path,
) -> tuple[dict[str, str], set[str]]:
    functional_set = planning_dir / "functional-set.md"
    plan = planning_dir / "plan.md"
    for path in (functional_set, plan):
        if not path.is_file():
            fail(f"missing {fs_id} Planning artifact: {path.name}")

    fs_text = read(functional_set)
    id_matches = re.findall(
        r"^functional_set:\s*(FS-\d{3})\s*$",
        fs_text,
        flags=re.MULTILINE,
    )
    if len(id_matches) != 1 or id_matches[0] != fs_id:
        fail(
            f"{fs_id} functional-set.md identity mismatch: "
            "expected exactly one matching functional_set identity"
        )

    revision_matches = re.findall(
        r"^design_revision:\s*([^\s]+)\s*$",
        fs_text,
        flags=re.MULTILINE,
    )
    if len(revision_matches) != 1 or not re.fullmatch(r"[0-9a-f]{40}", revision_matches[0]):
        fail(
            f"{fs_id} must contain exactly one well-formed "
            "40-character lowercase Git design_revision"
        )
    revision = revision_matches[0]
    if fs_id == "FS-001" and revision != FS001_DESIGN_REVISION:
        fail("FS-001 does not identify its exact normative Design revision")

    return parse_specification(spec_path, fs_id)

def collect_requirement_state(
    planning_root: Path = PLANNING_ROOT,
    specs_root: Path = SPECS_ROOT,
) -> tuple[dict[str, str], set[str]]:
    requirements: dict[str, str] = {}
    inactive: set[str] = set()
    for fs_id, _, planning_dir, spec_path in discover_functional_sets(planning_root, specs_root):
        parsed, parsed_inactive = validate_functional_set(fs_id, planning_dir, spec_path)
        overlap = set(requirements) & set(parsed)
        if overlap:
            fail(f"duplicate normative requirement identities across specifications: {sorted(overlap)}")
        requirements.update(parsed)
        inactive.update(parsed_inactive)
    return requirements, inactive


def collect_requirements(
    planning_root: Path = PLANNING_ROOT,
    specs_root: Path = SPECS_ROOT,
) -> dict[str, str]:
    requirements, _ = collect_requirement_state(planning_root, specs_root)
    return requirements


def collect_spec_requirement_state(
    specs_root: Path = SPECS_ROOT,
) -> tuple[dict[str, str], set[str]]:
    if not specs_root.is_dir():
        fail("repo/specs must exist")
    requirements: dict[str, str] = {}
    inactive: set[str] = set()
    seen_fs: set[str] = set()
    for spec_path in sorted(specs_root.glob("FS-*.md")):
        match = FS_BASENAME_RE.fullmatch(spec_path.stem)
        if not match:
            fail(f"invalid Functional Set specification name: {spec_path.name}")
        fs_id = match.group(1)
        if fs_id in seen_fs:
            fail(f"duplicate Functional Set specification identity: {fs_id}")
        seen_fs.add(fs_id)
        parsed, parsed_inactive = parse_specification(spec_path, fs_id)
        overlap = set(requirements) & set(parsed)
        if overlap:
            fail(f"duplicate normative requirement identities across specifications: {sorted(overlap)}")
        requirements.update(parsed)
        inactive.update(parsed_inactive)
    if not requirements:
        fail("repo/specs contains no normative requirements")
    return requirements, inactive


def installed_framework(source_record: Path = FRAMEWORK_SOURCE_RECORD) -> bool:
    return source_record.is_file()


def load_manifest(path: Path = MANIFEST) -> dict:
    try:
        data = json.loads(read(path))
    except json.JSONDecodeError as exc:
        fail(f"invalid Requirement Evaluation Manifest JSON: {exc}")
    if data.get("version") != 1 or not isinstance(data.get("bindings"), list):
        fail("invalid Requirement Evaluation Manifest structure")
    return data


def validate_manifest_data(
    requirements: dict[str, str],
    data: dict,
    tasks: tuple[str, ...] = TASKS,
    required_bindings: set[str] | None = None,
    forbidden_bindings: set[str] | None = None,
) -> None:
    bindings = data["bindings"]
    seen: set[str] = set()
    task_to_requirements = {task: set() for task in tasks}

    for binding in bindings:
        if not isinstance(binding, dict):
            fail("manifest binding must be an object")
        req = binding.get("requirement")
        bound_tasks = binding.get("tasks")
        if req not in requirements:
            fail(f"manifest references unknown requirement: {req}")
        if requirements[req] not in {"M", "B"}:
            fail(f"manifest references requirement without active mechanical evaluation: {req}")
        if req in seen:
            fail(f"duplicate manifest binding for requirement: {req}")
        seen.add(req)
        if (
            not isinstance(bound_tasks, list)
            or not bound_tasks
            or len(bound_tasks) != len(set(bound_tasks))
        ):
            fail(f"invalid task list for {req}")
        for task in bound_tasks:
            if task not in tasks:
                fail(f"manifest references unknown Validation task: {task}")
            task_to_requirements[task].add(req)

    if required_bindings is not None:
        missing = sorted(required_bindings - seen)
        if missing:
            fail(f"active mechanically evaluated requirements without manifest bindings: {missing}")

    if forbidden_bindings is not None:
        forbidden = sorted(forbidden_bindings & seen)
        if forbidden:
            fail(f"inactive requirements must not have manifest bindings: {forbidden}")

    unjustified = sorted(task for task, reqs in task_to_requirements.items() if not reqs)
    if unjustified:
        fail(f"Validation tasks without current normative justification: {unjustified}")


PRODUCT_CLASS_RE = re.compile(r"^(?:\*\*)?Classification: ([MSB])(?:\*\*)?$")
PRODUCT_STATE_RE = re.compile(r"^\*\*State: ([^*\n]+)\*\*$")


def collect_product_requirement_state(
    specs_root: Path = PRODUCT_SPECS_ROOT,
) -> tuple[dict[str, str], set[str]]:
    if not specs_root.is_dir():
        fail("product/specs must exist")
    requirements: dict[str, str] = {}
    inactive: set[str] = set()
    for spec_path in sorted(specs_root.glob("FS-*.md")):
        text = read(spec_path)
        headings = list(REQ_HEADING_RE.finditer(text))
        for index, match in enumerate(headings):
            req = match.group(1)
            if req in requirements:
                fail(f"duplicate product normative requirement identity: {req}")
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            block = text[match.end():end]
            classes = [m.group(1) for line in block.splitlines() if (m := PRODUCT_CLASS_RE.match(line))]
            if len(classes) != 1:
                fail(f"product requirement {req} must have exactly one Classification")
            requirements[req] = classes[0]
            states = [m.group(1) for line in block.splitlines() if (m := PRODUCT_STATE_RE.match(line))]
            if len(states) > 1:
                fail(f"product requirement {req} has multiple State declarations")
            if states and states[0] != "Inactive":
                fail(f"product requirement {req} State must be Inactive when explicitly present")
            if states:
                inactive.add(req)
    return requirements, inactive


def validate_product_entrypoint_text(text: str) -> None:
    if text != CANONICAL_PRODUCT_ENTRYPOINT:
        fail(
            "product/scripts/validate must be the canonical thin launcher only; "
            "substantive product Validation belongs under product/validation/"
        )


def product_task_names(entrypoint: Path = PRODUCT_ENTRYPOINT) -> tuple[str, ...]:
    cp = subprocess.run(
        [str(entrypoint), "--list-tasks"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if cp.returncode != 0:
        fail(f"product Validation task enumeration failed: {cp.stderr.strip() or cp.stdout.strip()}")
    tasks = tuple(line for line in cp.stdout.splitlines() if line)
    if len(tasks) != len(set(tasks)):
        fail("product Validation task enumeration contains duplicates")
    return tasks


def validate_product_manifest_contract(
    requirements: dict[str, str],
    inactive: set[str],
    data: dict,
    tasks: tuple[str, ...],
) -> None:
    required = {
        req for req, classification in requirements.items()
        if classification in {"M", "B"} and req not in inactive
    }
    forbidden = {
        req for req, classification in requirements.items()
        if classification == "S" or req in inactive
    }
    seen: set[str] = set()
    for binding in data["bindings"]:
        if not isinstance(binding, dict):
            fail("product manifest binding must be an object")
        req = binding.get("requirement")
        bound_tasks = binding.get("tasks")
        if req not in requirements:
            fail(f"product manifest references unknown requirement: {req}")
        if req in forbidden:
            fail(f"product manifest references requirement without active mechanical evaluation: {req}")
        if req in seen:
            fail(f"duplicate product manifest binding for requirement: {req}")
        seen.add(req)
        if (
            not isinstance(bound_tasks, list)
            or not bound_tasks
            or len(bound_tasks) != len(set(bound_tasks))
            or not all(isinstance(task, str) and task for task in bound_tasks)
        ):
            fail(f"invalid product task list for {req}")
        unknown = sorted(set(bound_tasks) - set(tasks))
        if unknown:
            fail(f"product manifest references unknown Validation tasks: {unknown}")
    missing = sorted(required - seen)
    if missing:
        fail(f"active mechanically evaluated product requirements without manifest bindings: {missing}")


def task_design_corpus() -> None:
    if not DESIGN.is_dir():
        fail("repo/design must exist")
    files = [p for p in DESIGN.rglob("*") if p.is_file()]
    if not files:
        fail("repo/design contains no Design documents")
    non_markdown = [str(p.relative_to(ROOT)) for p in files if p.suffix.lower() != ".md"]
    if non_markdown:
        fail(f"canonical Design corpus contains non-Markdown files: {non_markdown}")



def candidate_paths() -> list[str]:
    cp = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if cp.returncode != 0:
        fail(f"could not enumerate maintained candidate paths: {cp.stderr.decode(errors='replace')}")
    return [value.decode("utf-8") for value in cp.stdout.split(b"\0") if value]


def validate_structure_policy_data(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        fail("structural policy must be a JSON object")
    if set(data) != {"version", "root", "repo", "product"}:
        fail("structural policy contains missing or unknown top-level keys")
    if data.get("version") != 1 or isinstance(data.get("version"), bool):
        fail("structural policy version must be integer 1")

    root = data.get("root")
    repo = data.get("repo")
    product = data.get("product")
    if not isinstance(root, dict) or set(root) != {"files", "directories"}:
        fail("structural policy root section is invalid")
    if not isinstance(repo, dict) or set(repo) != {"directories"}:
        fail("structural policy repo section is invalid")
    if not isinstance(product, dict) or set(product) != {"directories", "required_when_present"}:
        fail("structural policy product section is invalid")

    def names(value: object, label: str) -> list[str]:
        if not isinstance(value, list):
            fail(f"structural policy {label} must be an array")
        if len(value) != len(set(value)):
            fail(f"structural policy {label} contains duplicate entries")
        for name in value:
            if (
                not isinstance(name, str)
                or not name
                or name in {".", ".."}
                or "/" in name
                or "\\" in name
                or Path(name).is_absolute()
            ):
                fail(f"structural policy {label} contains invalid direct-child name: {name!r}")
        return value

    root_files = names(root["files"], "root.files")
    root_dirs = names(root["directories"], "root.directories")
    names(repo["directories"], "repo.directories")
    product_dirs = names(product["directories"], "product.directories")
    product_required = names(product["required_when_present"], "product.required_when_present")

    overlap = sorted(set(root_files) & set(root_dirs))
    if overlap:
        fail(f"structural policy root file/directory overlap: {overlap}")
    missing_required = sorted(set(product_required) - set(product_dirs))
    if missing_required:
        fail(
            "structural policy product.required_when_present is not a subset "
            f"of product.directories: {missing_required}"
        )
    return data


def load_structure_policy(path: Path = STRUCTURE_POLICY) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"required structural policy missing: {path}")
    except json.JSONDecodeError as exc:
        fail(f"invalid structural policy JSON: {exc}")
    return validate_structure_policy_data(data)


def validate_structural_paths(
    paths: list[str],
    policy: dict[str, object] | None = None,
) -> None:
    if policy is None:
        policy = load_structure_policy()
    root = policy["root"]
    repo = policy["repo"]
    product = policy["product"]
    root_files = set(root["files"])
    root_dirs = set(root["directories"])
    repo_children = set(repo["directories"])
    product_children = set(product["directories"])

    for raw in paths:
        parts = Path(raw).parts
        if not parts:
            continue
        top = parts[0]
        if len(parts) == 1:
            if top not in root_files:
                fail(f"unauthorized maintained repository-root file: {raw}")
            continue
        if top not in root_dirs:
            fail(f"unauthorized maintained repository-root role: {top}")
        if top == "repo":
            child = parts[1]
            if child not in repo_children:
                fail(f"unauthorized repo/ direct-child role: {child}")
            if len(parts) == 2:
                fail(f"maintained direct files are not permitted beneath repo/: {raw}")
        if top == "product":
            child = parts[1]
            if child not in product_children:
                fail(f"unauthorized product/ direct-child role: {child}")
            if len(parts) == 2:
                fail(f"maintained direct files are not permitted beneath product/: {raw}")
        if top == "scripts":
            if len(parts) != 2 or parts[1] != "validate":
                fail(f"unauthorized repository-root scripts entry: {raw}")


def task_repository_structure() -> None:
    paths = candidate_paths()
    policy = load_structure_policy()
    validate_structural_paths(paths, policy)
    product_paths = [
        Path(raw).parts for raw in paths
        if Path(raw).parts and Path(raw).parts[0] == "product"
    ]
    if product_paths:
        present = {parts[1] for parts in product_paths if len(parts) >= 2}
        required = set(policy["product"]["required_when_present"])
        missing = sorted(required - present)
        if missing:
            fail(f"product/ is missing required baseline roles: {missing}")


def task_planning_structure() -> None:
    if installed_framework():
        return
    collect_requirements()


def task_manifest_integrity() -> None:
    if installed_framework():
        requirements, inactive = collect_spec_requirement_state()
    else:
        requirements, inactive = collect_requirement_state()
    required_bindings = {
        req
        for req, classification in requirements.items()
        if classification in {"M", "B"} and req not in inactive
    }
    validate_manifest_data(
        requirements,
        load_manifest(),
        required_bindings=required_bindings,
        forbidden_bindings=inactive,
    )

    if PRODUCT_ROOT.is_dir():
        product_requirements, product_inactive = collect_product_requirement_state()
        validate_product_manifest_contract(
            product_requirements,
            product_inactive,
            load_manifest(PRODUCT_MANIFEST),
            product_task_names(),
        )


def task_validation_entrypoint() -> None:
    text = read(ENTRYPOINT)
    if not os.access(ENTRYPOINT, os.X_OK):
        fail("repo/scripts/validate must be executable")
    if "repo/validation/validate_framework.py" not in text:
        fail("repo/scripts/validate must delegate to the project-native validator")
    cp = subprocess.run(
        [str(ENTRYPOINT), "--task", "__invalid_required_task__"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if cp.returncode == 0:
        fail("canonical framework Validation did not fail for an invalid required task")

    root_text = read(ROOT_ENTRYPOINT)
    if not os.access(ROOT_ENTRYPOINT, os.X_OK):
        fail("scripts/validate must be executable")
    if 'ROOT / "repo" / "scripts" / "validate"' not in root_text:
        fail("scripts/validate must delegate to repo/scripts/validate")
    if 'ROOT / "product"' not in root_text or '"scripts" / "validate"' not in root_text:
        fail("scripts/validate must compose required product/scripts/validate when product/ exists")

    if PRODUCT_ROOT.is_dir():
        product_text = read(PRODUCT_ENTRYPOINT)
        if not os.access(PRODUCT_ENTRYPOINT, os.X_OK):
            fail("product/scripts/validate must be executable")
        validate_product_entrypoint_text(product_text)
        if not PRODUCT_VALIDATOR.is_file():
            fail("product/validation/validate_product.py must exist")
        product_task_names()
        invalid = subprocess.run(
            [str(PRODUCT_ENTRYPOINT), "--task", "__invalid_required_task__"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if invalid.returncode == 0:
            fail("canonical product Validation did not fail for an unknown task")


def task_docs_alignment() -> None:
    readme = read(README)
    agents = read(AGENTS)
    for term in ("Design", "Planning", "Build", "Validation", "Semantic Review", "Acceptance"):
        if term not in readme:
            fail(f"README missing lifecycle term: {term}")
    active_surfaces = ["repo/design/", "repo/specs/", "product/", "scripts/validate", "repo/scripts/validate", "main"]
    if not installed_framework():
        active_surfaces.append("repo/planning/")
    for value in active_surfaces:
        if value not in readme:
            fail(f"README missing active surface: {value}")
    for route in ("→ **Design**", "→ **Planning**", "→ **Build**"):
        if route not in agents:
            fail(f"AGENTS.md missing defect route: {route}")
    if "`product/` is the generic product-owned domain" not in agents:
        fail("AGENTS.md must describe generic product ownership")
    if "Closed architectural boundaries are default-deny" not in agents:
        fail("AGENTS.md must describe closed architectural boundaries")
    retired = (
        "canonical mechanical Conformance",
        "accepted Governance",
        "Governance acceptance",
        "FS0 Conformance",
        "Assurance —",
        "Conformance —",
        "Authority —",
    )
    combined = readme + "\n" + agents
    for phrase in retired:
        if phrase in combined:
            fail(f"active documentation retains retired wording: {phrase}")


def task_ci_delegation() -> None:
    if OLD_WORKFLOW.exists():
        fail("retired fs0-conformance workflow remains active")
    text = read(WORKFLOW)
    if "name: Validation" not in text or "run: ./scripts/validate" not in text:
        fail("CI must use Validation terminology and invoke repository-wide Validation")
    if "run: ./repo/scripts/validate" in text or "run: ./product/scripts/validate" in text:
        fail("CI must delegate domain selection to scripts/validate")
    if "repo/validation/validate_framework.py" in text:
        fail("CI must not bypass canonical Validation entry points")
    if "Conformance" in text or "conformance" in text:
        fail("active CI retains retired Conformance terminology")


def aggregate(results: list[bool]) -> bool:
    return all(results)


def task_validation_gate() -> None:
    if set(TASKS) != set(TASK_FUNCTIONS):
        fail("registered Validation task set is incomplete")
    if select_tasks([]) != list(TASKS):
        fail("default canonical Validation must select every registered required task")
    if aggregate([True, True, False]):
        fail("Validation aggregation must fail when a required task fails")
    if not aggregate([True, True, True]):
        fail("Validation aggregation must pass when all required tasks pass")


def write_fixture_fs(
    planning_root: Path,
    specs_root: Path,
    basename: str,
    fs_id: str,
    revision: str,
    requirement_id: str,
    classification: str,
) -> None:
    planning_dir = planning_root / basename
    planning_dir.mkdir(parents=True)
    (planning_dir / "functional-set.md").write_text(
        f"---\nfunctional_set: {fs_id}\ntitle: Fixture\ndesign_revision: {revision}\n---\n",
        encoding="utf-8",
    )
    (planning_dir / "plan.md").write_text("# Fixture Plan\n", encoding="utf-8")
    (specs_root / f"{basename}.md").write_text(
        f"# {fs_id} — Fixture\n\n"
        f"### {requirement_id} — Fixture requirement\n\n"
        f"**Classification: {classification}**\n\nFixture obligation.\n",
        encoding="utf-8",
    )


def expect_failure(fn: Callable[[], object], contains: str) -> None:
    try:
        fn()
    except Exception as exc:
        if contains not in str(exc):
            fail(f"regression expected diagnostic containing {contains!r}, observed: {exc}")
    else:
        fail(f"regression expected failure containing {contains!r}")


def task_framework_regression() -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip()

    policy = load_structure_policy()
    expected_policy = {
        "version": 1,
        "root": {
            "files": [".gitignore", "AGENTS.md", "LICENSE", "README.md"],
            "directories": [".github", "product", "repo", "scripts", "user"],
        },
        "repo": {
            "directories": ["design", "planning", "scripts", "specs", "src", "validation"],
        },
        "product": {
            "directories": ["design", "planning", "scripts", "specs", "src", "validation"],
            "required_when_present": ["design", "scripts", "specs", "validation"],
        },
    }
    if not installed_framework() and policy != expected_policy:
        fail("canonical supplier structural policy is not compatible with the pre-FS-005 default")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        custom_path = root / "structure-policy.json"
        custom = json.loads(json.dumps(policy))
        custom["root"]["files"] = sorted(set(custom["root"]["files"]) | {"application.json"})
        custom["root"]["directories"] = sorted(set(custom["root"]["directories"]) | {"runtime"})
        custom["repo"]["directories"] = sorted(
            set(custom["repo"]["directories"]) | {"application"}
        )
        custom["product"]["directories"] = sorted(
            set(custom["product"]["directories"]) | {"application"}
        )
        custom_path.write_text(json.dumps(custom, indent=2) + "\n", encoding="utf-8")
        loaded = load_structure_policy(custom_path)

        source_record = root / "framework-source.json"
        source_record.write_text(
            json.dumps(
                {
                    "schema_version": "1",
                    "repo_spec_source_revision": "a" * 40,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        source_record_before = source_record.read_bytes()
        if not installed_framework(source_record):
            fail("adapted-policy regression did not recognize installed framework identity")
        if source_record.read_bytes() != source_record_before:
            fail("adapted structural policy unexpectedly changed framework source identity")
        if json.loads(source_record.read_text(encoding="utf-8"))[
            "repo_spec_source_revision"
        ] != "a" * 40:
            fail("adapted structural policy obscured supplying framework revision")

        validate_structural_paths(
            [
                "application.json",
                "runtime/state.json",
                "repo/validation/structure-policy.json",
                "repo/application/state.json",
                "product/design/README.md",
                "product/application/state.json",
                "scripts/validate",
            ],
            loaded,
        )
        expect_failure(
            lambda: validate_structural_paths(["undeclared.json"], loaded),
            "unauthorized maintained repository-root file",
        )
        expect_failure(
            lambda: validate_structural_paths(["undeclared/value"], loaded),
            "unauthorized maintained repository-root role",
        )
        expect_failure(
            lambda: validate_structural_paths(
                ["repo/undeclared/state.json"],
                loaded,
            ),
            "unauthorized repo/ direct-child role",
        )
        expect_failure(
            lambda: validate_structural_paths(
                ["product/undeclared/state.json"],
                loaded,
            ),
            "unauthorized product/ direct-child role",
        )
        expect_failure(
            lambda: load_structure_policy(root / "missing.json"),
            "required structural policy missing",
        )
        malformed = root / "malformed.json"
        malformed.write_text("{bad json\n", encoding="utf-8")
        expect_failure(
            lambda: load_structure_policy(malformed),
            "invalid structural policy JSON",
        )
        invalid_cases = [
            {**custom, "unknown": True},
            {**custom, "root": {"files": ["duplicate", "duplicate"], "directories": custom["root"]["directories"]}},
            {**custom, "root": {"files": ["shared"], "directories": ["shared"]}},
            {**custom, "repo": {"directories": ["bad/name"]}},
            {**custom, "product": {"directories": ["design"], "required_when_present": ["validation"]}},
        ]
        for index, invalid in enumerate(invalid_cases):
            fixture = root / f"invalid-{index}.json"
            fixture.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
            expect_failure(
                lambda fixture=fixture: load_structure_policy(fixture),
                "structural policy",
            )

        required_policy = json.loads(json.dumps(policy))
        required_policy["product"]["directories"] = sorted(
            set(required_policy["product"]["directories"]) | {"application"}
        )
        required_policy["product"]["required_when_present"] = sorted(
            set(required_policy["product"]["required_when_present"]) | {"application"}
        )
        required_paths = [
            "product/design/README.md",
            "product/scripts/validate",
            "product/specs/README.md",
            "product/src/app.py",
            "product/validation/validate_product.py",
        ]

        original_candidate_paths = globals()["candidate_paths"]
        original_load_structure_policy = globals()["load_structure_policy"]
        try:
            globals()["candidate_paths"] = lambda: list(required_paths)
            globals()["load_structure_policy"] = lambda path=STRUCTURE_POLICY: required_policy
            expect_failure(
                task_repository_structure,
                "product/ is missing required baseline roles: ['application']",
            )
        finally:
            globals()["candidate_paths"] = original_candidate_paths
            globals()["load_structure_policy"] = original_load_structure_policy

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planning = root / "planning"
        specs = root / "specs"
        planning.mkdir()
        specs.mkdir()

        write_fixture_fs(
            planning,
            specs,
            "FS-998-fixture",
            "FS-998",
            head,
            "FS-998-NR-001",
            "S",
        )
        reqs = collect_requirements(planning, specs)
        if reqs != {"FS-998-NR-001": "S"}:
            fail("generic later Functional Set discovery/parsing regression failed")

        (specs / "FS-998-fixture.md").unlink()
        expect_failure(
            lambda: collect_requirements(planning, specs),
            "correspondence mismatch",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planning = root / "planning"
        specs = root / "specs"
        planning.mkdir()
        specs.mkdir()

        foreign = root / "foreign"
        foreign.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main"],
            cwd=foreign,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(["git", "config", "user.name", "repo-spec test"], cwd=foreign, check=True)
        subprocess.run(["git", "config", "user.email", "repo-spec-test@local.invalid"], cwd=foreign, check=True)
        (foreign / "design.md").write_text("foreign design\n", encoding="utf-8")
        subprocess.run(["git", "add", "design.md"], cwd=foreign, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Foreign Design"],
            cwd=foreign,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        foreign_revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=foreign,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout.strip()

        if git_commit_exists(foreign_revision):
            fail("foreign Design commit unexpectedly exists in current repository")

        write_fixture_fs(
            planning,
            specs,
            "FS-998-fixture",
            "FS-998",
            foreign_revision,
            "FS-998-NR-001",
            "M",
        )
        reqs = collect_requirements(planning, specs)
        if reqs != {"FS-998-NR-001": "M"}:
            fail("portable foreign Design revision regression failed")

        fs_path = planning / "FS-998-fixture" / "functional-set.md"
        text = fs_path.read_text(encoding="utf-8").replace(
            "functional_set: FS-998",
            "functional_set: FS-997",
        )
        fs_path.write_text(text.replace("0" * 40, head), encoding="utf-8")
        expect_failure(
            lambda: collect_requirements(planning, specs),
            "identity mismatch",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planning = root / "planning"
        specs = root / "specs"
        planning.mkdir()
        specs.mkdir()

        write_fixture_fs(
            planning, specs, "FS-998-fixture", "FS-998", head,
            "FS-997-NR-001", "M",
        )
        expect_failure(
            lambda: collect_requirements(planning, specs),
            "requirement identity does not match owning Functional Set",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planning = root / "planning"
        specs = root / "specs"
        planning.mkdir()
        specs.mkdir()

        write_fixture_fs(
            planning, specs, "FS-998-fixture", "FS-998", head,
            "FS-998-NR-001", "M",
        )
        spec_path = specs / "FS-998-fixture.md"
        spec_text = spec_path.read_text(encoding="utf-8")
        spec_path.write_text(
            spec_text.replace("**Classification: M**", "**Classification: X**"),
            encoding="utf-8",
        )
        expect_failure(
            lambda: collect_requirements(planning, specs),
            "Classification of M, S, or B",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planning = root / "planning"
        specs = root / "specs"
        planning.mkdir()
        specs.mkdir()

        write_fixture_fs(
            planning, specs, "FS-998-fixture", "FS-998", head,
            "FS-998-NR-001", "M",
        )
        spec_path = specs / "FS-998-fixture.md"
        with spec_path.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n### FS-998-NR-001 — Duplicate fixture requirement\n\n"
                "**Classification: M**\n\nDuplicate obligation.\n"
            )
        expect_failure(
            lambda: collect_requirements(planning, specs),
            "duplicate normative requirement identity",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planning = root / "planning"
        specs = root / "specs"
        planning.mkdir()
        specs.mkdir()

        write_fixture_fs(
            planning, specs, "FS-998-Fixture_Name", "FS-998", head,
            "FS-998-NR-001", "M",
        )
        reqs = collect_requirements(planning, specs)
        if reqs != {"FS-998-NR-001": "M"}:
            fail("descriptive Functional Set suffix must not create a second identity grammar")

        spec_path = specs / "FS-998-Fixture_Name.md"
        base_spec = spec_path.read_text(encoding="utf-8")
        for malformed_heading in (
            "FS-998-NR-01 — Malformed requirement",
            "FS-998-NR001 — Malformed requirement",
            "FS998-NR-001 — Malformed requirement",
            "FS-998-REQ-001 — Malformed requirement",
        ):
            spec_path.write_text(
                base_spec
                + f"\n### {malformed_heading}\n\n"
                + "**Classification: M**\n\nMalformed.\n",
                encoding="utf-8",
            )
            expect_failure(
                lambda: collect_requirements(planning, specs),
                "malformed normative requirement heading",
            )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planning = root / "planning"
        specs = root / "specs"
        planning.mkdir()
        specs.mkdir()

        write_fixture_fs(
            planning, specs, "FS-998-fixture", "FS-998", head,
            "FS-998-NR-001", "M",
        )
        spec_path = specs / "FS-998-fixture.md"
        spec_text = spec_path.read_text(encoding="utf-8")
        spec_path.write_text(
            spec_text.replace(
                "**Classification: M**\n\nFixture obligation.",
                "**Classification: M**\n\n**Classification: S**\n\nFixture obligation.",
            ),
            encoding="utf-8",
        )
        expect_failure(
            lambda: collect_requirements(planning, specs),
            "exactly one Classification",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planning = root / "planning"
        specs = root / "specs"
        planning.mkdir()
        specs.mkdir()

        write_fixture_fs(
            planning, specs, "FS-998-fixture", "FS-998", head,
            "FS-998-NR-001", "M",
        )
        fs_path = planning / "FS-998-fixture" / "functional-set.md"
        fs_text = fs_path.read_text(encoding="utf-8")
        fs_path.write_text(
            fs_text.replace(
                "functional_set: FS-998",
                "functional_set: FS-998\nfunctional_set: FS-998",
            ),
            encoding="utf-8",
        )
        expect_failure(
            lambda: collect_requirements(planning, specs),
            "exactly one matching functional_set",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planning = root / "planning"
        specs = root / "specs"
        planning.mkdir()
        specs.mkdir()

        write_fixture_fs(
            planning, specs, "FS-998-fixture", "FS-998", head,
            "FS-998-NR-001", "M",
        )
        fs_path = planning / "FS-998-fixture" / "functional-set.md"
        fs_text = fs_path.read_text(encoding="utf-8")
        fs_path.write_text(
            fs_text.replace(
                f"design_revision: {head}",
                f"design_revision: {head}\ndesign_revision: {head}",
            ),
            encoding="utf-8",
        )
        expect_failure(
            lambda: collect_requirements(planning, specs),
            "exactly one well-formed",
        )

    # Repository-root Validation composes framework and optional product Validation.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scripts_dir = root / "scripts"
        repo_scripts = root / "repo" / "scripts"
        product_scripts = root / "product" / "scripts"
        scripts_dir.mkdir(parents=True)
        repo_scripts.mkdir(parents=True)
        product_scripts.mkdir(parents=True)

        shutil.copy2(ROOT_ENTRYPOINT, scripts_dir / "validate")
        (scripts_dir / "validate").chmod(0o755)

        framework = repo_scripts / "validate"
        framework.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        framework.chmod(0o755)

        completed = subprocess.run([str(scripts_dir / "validate")], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode == 0:
            fail("root Validation must fail when product/ exists but canonical product Validation is absent")

        product = product_scripts / "validate"
        product.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        product.chmod(0o644)
        completed = subprocess.run([str(scripts_dir / "validate")], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode == 0:
            fail("root Validation must fail when product Validation exists but is not executable")

        product.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
        product.chmod(0o755)
        completed = subprocess.run([str(scripts_dir / "validate")], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode == 0:
            fail("root Validation must fail when product Validation fails")

        product.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        product.chmod(0o755)
        completed = subprocess.run([str(scripts_dir / "validate")], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode != 0:
            fail("root Validation must pass when framework and product Validation pass")

    # Product requirement state uses the repository's canonical explicit
    # Inactive form; absence of State means active.
    with tempfile.TemporaryDirectory() as tmp:
        specs = Path(tmp)
        spec = specs / "FS-998-state-fixture.md"
        spec.write_text(
            "# FS-998 — State Fixture\n\n"
            "### FS-998-NR-001 — Inactive mechanical\n\n"
            "**Classification: M**\n\n"
            "**State: Inactive**\n\n"
            "Fixture.\n\n"
            "### FS-998-NR-002 — Inactive both\n\n"
            "**Classification: B**\n\n"
            "**State: Inactive**\n\n"
            "Fixture.\n\n"
            "### FS-998-NR-003 — Active semantic\n\n"
            "**Classification: S**\n\n"
            "Fixture.\n",
            encoding="utf-8",
        )
        product_requirements, product_inactive = collect_product_requirement_state(specs)
        if product_inactive != {"FS-998-NR-001", "FS-998-NR-002"}:
            fail("canonical product Inactive-state regression failed")
        validate_product_manifest_contract(
            product_requirements,
            product_inactive,
            {"version": 1, "bindings": []},
            (),
        )

        spec.write_text(
            spec.read_text(encoding="utf-8").replace(
                "**State: Inactive**",
                "**State: Active**",
                1,
            ),
            encoding="utf-8",
        )
        expect_failure(
            lambda: collect_product_requirement_state(specs),
            "State must be Inactive",
        )

    # Product Validation entrypoint must remain composition only.
    validate_product_entrypoint_text(CANONICAL_PRODUCT_ENTRYPOINT)
    expect_failure(
        lambda: validate_product_entrypoint_text(CANONICAL_PRODUCT_ENTRYPOINT + "\necho substantive-product-check\n"),
        "canonical thin launcher only",
    )

    # Generic product Validation contract regression.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        specs = root / "specs"
        specs.mkdir()
        (specs / "FS-998-fixture.md").write_text(
            "# FS-998 — Fixture\n\n"
            "### FS-998-NR-001 — Mechanical\n\nClassification: M\n\nMechanical.\n\n"
            "### FS-998-NR-002 — Semantic\n\nClassification: S\n\nSemantic.\n",
            encoding="utf-8",
        )
        reqs, inactive = collect_product_requirement_state(specs)
        valid = {
            "version": 1,
            "bindings": [{"requirement": "FS-998-NR-001", "tasks": ["check"]}],
        }
        validate_product_manifest_contract(reqs, inactive, valid, ("check",))
        expect_failure(
            lambda: validate_product_manifest_contract(
                reqs, inactive, {"version": 1, "bindings": []}, ("check",)
            ),
            "without manifest bindings",
        )
        expect_failure(
            lambda: validate_product_manifest_contract(
                reqs, inactive,
                {"version": 1, "bindings": [{"requirement": "FS-998-NR-002", "tasks": ["check"]}]},
                ("check",),
            ),
            "without active mechanical evaluation",
        )
        expect_failure(
            lambda: validate_product_manifest_contract(
                reqs, inactive,
                {"version": 1, "bindings": [{"requirement": "FS-998-NR-001", "tasks": ["missing"]}]},
                ("check",),
            ),
            "unknown Validation tasks",
        )

    # Installed framework snapshots may omit framework-development Planning history.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        specs = root / "specs"
        specs.mkdir()
        source_record = root / "framework-source.json"
        source_record.write_text("{}\n", encoding="utf-8")
        (specs / "FS-998-fixture.md").write_text(
            "# FS-998 — Fixture\n\n"
            "### FS-998-NR-001 — Fixture requirement\n\n"
            "**Classification: M**\n\nFixture obligation.\n",
            encoding="utf-8",
        )
        if not installed_framework(source_record):
            fail("installed framework source record regression failed")
        requirements, inactive = collect_spec_requirement_state(specs)
        if requirements != {"FS-998-NR-001": "M"} or inactive:
            fail("installed framework spec-only requirement regression failed")

    # Retired I evaluation classification is invalid.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planning = root / "planning"
        specs = root / "specs"
        planning.mkdir()
        specs.mkdir()

        write_fixture_fs(
            planning, specs, "FS-998-fixture", "FS-998", head,
            "FS-998-NR-001", "I",
        )
        expect_failure(
            lambda: collect_requirement_state(planning, specs),
            "Classification of M, S, or B",
        )

    # Requirement state is separate from evaluation classification.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        planning = root / "planning"
        specs = root / "specs"
        planning.mkdir()
        specs.mkdir()

        write_fixture_fs(
            planning, specs, "FS-998-fixture", "FS-998", head,
            "FS-998-NR-001", "M",
        )
        spec_path = specs / "FS-998-fixture.md"
        active_text = spec_path.read_text(encoding="utf-8")
        inactive_text = active_text.replace(
            "**Classification: M**",
            "**Classification: M**\n\n**State: Inactive**",
            1,
        )
        spec_path.write_text(inactive_text, encoding="utf-8")

        fixture_requirements, fixture_inactive = collect_requirement_state(
            planning, specs
        )
        if fixture_requirements != {"FS-998-NR-001": "M"}:
            fail("inactive requirement must retain its evaluation classification")
        if fixture_inactive != {"FS-998-NR-001"}:
            fail("inactive requirement state was not parsed")

        validate_manifest_data(
            fixture_requirements,
            {"version": 1, "bindings": []},
            tasks=(),
            required_bindings=set(),
            forbidden_bindings=fixture_inactive,
        )
        expect_failure(
            lambda: validate_manifest_data(
                fixture_requirements,
                {
                    "version": 1,
                    "bindings": [
                        {
                            "requirement": "FS-998-NR-001",
                            "tasks": ["planning-structure"],
                        }
                    ],
                },
                tasks=("planning-structure",),
                required_bindings=set(),
                forbidden_bindings=fixture_inactive,
            ),
            "inactive requirements must not have manifest bindings",
        )

        spec_path.write_text(active_text, encoding="utf-8")
        reactivated, reactivated_inactive = collect_requirement_state(
            planning, specs
        )
        if reactivated != {"FS-998-NR-001": "M"} or reactivated_inactive:
            fail("reactivation by removing State: Inactive failed")

    for state_marker, diagnostic in (
        ("**State: Active**", "State must be Inactive"),
        (
            "**State: Inactive**\n\n**State: Inactive**",
            "duplicate State markers",
        ),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planning = root / "planning"
            specs = root / "specs"
            planning.mkdir()
            specs.mkdir()

            write_fixture_fs(
                planning, specs, "FS-998-fixture", "FS-998", head,
                "FS-998-NR-001", "M",
            )
            spec_path = specs / "FS-998-fixture.md"
            fixture_text = spec_path.read_text(encoding="utf-8")
            spec_path.write_text(
                fixture_text.replace(
                    "**Classification: M**",
                    "**Classification: M**\n\n" + state_marker,
                    1,
                ),
                encoding="utf-8",
            )
            expect_failure(
                lambda: collect_requirement_state(planning, specs),
                diagnostic,
            )

    requirements = {
        "FS-998-NR-001": "M",
        "FS-998-NR-002": "S",
    }
    expect_failure(
        lambda: validate_manifest_data(
            requirements,
            {"version": 1, "bindings": []},
            tasks=(),
            required_bindings={"FS-998-NR-001"},
        ),
        "without manifest bindings",
    )
    expect_failure(
        lambda: validate_manifest_data(
            requirements,
            {"version": 1, "bindings": [{"requirement": "FS-998-NR-999", "tasks": ["planning-structure"]}]},
        ),
        "unknown requirement",
    )
    expect_failure(
        lambda: validate_manifest_data(
            requirements,
            {"version": 1, "bindings": [{"requirement": "FS-998-NR-002", "tasks": ["planning-structure"]}]},
        ),
        "without active mechanical evaluation",
    )
    expect_failure(
        lambda: validate_manifest_data(
            requirements,
            {"version": 1, "bindings": [{"requirement": "FS-998-NR-001", "tasks": ["missing-task"]}]},
        ),
        "unknown Validation task",
    )

    validate_structural_paths([
        ".github/workflows/validation.yml",
        "README.md",
        "AGENTS.md",
        "repo/design/DP-001.md",
        "repo/src/pkg/module.py",
        "product/design/DP-100.md",
        "product/src/pkg/module.py",
        "user/session/notes.txt",
    ])
    for bad_path, diagnostic in (
        ("docs/readme.md", "repository-root role"),
        ("repo/tools/helper.py", "repo/ direct-child role"),
        ("repo/design", "direct files are not permitted beneath repo/"),
        ("product/lib/module.py", "product/ direct-child role"),
        ("product/src", "direct files are not permitted beneath product/"),
    ):
        expect_failure(lambda bad_path=bad_path: validate_structural_paths([bad_path]), diagnostic)

    all_current = {
        "FS-997-NR-001": "M",
        "FS-998-NR-001": "M",
    }
    expect_failure(
        lambda: validate_manifest_data(
            all_current,
            {
                "version": 1,
                "bindings": [
                    {"requirement": "FS-998-NR-001", "tasks": ["planning-structure"]}
                ],
            },
            tasks=("planning-structure",),
            required_bindings=set(all_current),
        ),
        "without manifest bindings",
    )

TASK_FUNCTIONS: dict[str, Callable[[], None]] = {
    "design-corpus": task_design_corpus,
    "repository-structure": task_repository_structure,
    "planning-structure": task_planning_structure,
    "manifest-integrity": task_manifest_integrity,
    "validation-entrypoint": task_validation_entrypoint,
    "docs-alignment": task_docs_alignment,
    "ci-delegation": task_ci_delegation,
    "validation-gate": task_validation_gate,
    "framework-regression": task_framework_regression,
}

def select_tasks(argv: list[str]) -> list[str]:
    if argv:
        if len(argv) != 2 or argv[0] != "--task":
            raise ValueError("usage")
        if argv[1] not in TASK_FUNCTIONS:
            raise KeyError(argv[1])
        return [argv[1]]
    return list(TASKS)


def main(argv: list[str]) -> int:
    try:
        selected = select_tasks(argv)
    except ValueError:
        print("usage: repo/scripts/validate [--task TASK]", file=sys.stderr)
        return 2
    except KeyError:
        print(f"unknown Validation task: {argv[1]}", file=sys.stderr)
        return 2

    results = []
    for name in selected:
        try:
            TASK_FUNCTIONS[name]()
        except Exception as exc:
            results.append(False)
            print(f"FAIL {name}: {exc}")
        else:
            results.append(True)
            print(f"PASS {name}")
    return 0 if aggregate(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
