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


TASK_FUNCTIONS: dict[str, Callable[[], None]] = {
    "design-corpus": task_design_corpus,
    "repository-structure": task_repository_structure,
    "planning-structure": task_planning_structure,
    "manifest-integrity": task_manifest_integrity,
    "validation-entrypoint": task_validation_entrypoint,
    "docs-alignment": task_docs_alignment,
    "ci-delegation": task_ci_delegation,
    "validation-gate": task_validation_gate,
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
