#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "product" / "validation" / "requirement-evaluation.json"
TASKS: dict[str, Callable[[], bool | None]] = {}


def fail(message: str) -> int:
    print(f"FAIL product-validation: {message}", file=sys.stderr)
    return 1


def load_manifest() -> dict:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load product Requirement Evaluation Manifest: {exc}") from exc
    if data.get("version") != 1 or not isinstance(data.get("bindings"), list):
        raise ValueError("invalid product Requirement Evaluation Manifest structure")
    return data


def manifest_tasks() -> list[str]:
    data = load_manifest()
    ordered: list[str] = []
    for binding in data["bindings"]:
        if not isinstance(binding, dict):
            raise ValueError("product manifest binding must be an object")
        tasks = binding.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise ValueError("product manifest binding requires a non-empty tasks list")
        for task in tasks:
            if not isinstance(task, str) or not task:
                raise ValueError("product validation task identity must be a non-empty string")
            if task not in TASKS:
                raise ValueError(f"product manifest references unknown task: {task}")
            if task not in ordered:
                ordered.append(task)
    return ordered


def execute(task: str) -> int:
    fn = TASKS.get(task)
    if fn is None:
        return fail(f"unknown product Validation task: {task}")
    result = fn()
    return 1 if result is False else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-tasks", action="store_true")
    parser.add_argument("--task")
    args = parser.parse_args(argv)

    if args.list_tasks and args.task:
        return fail("--list-tasks and --task are mutually exclusive")
    if args.list_tasks:
        for task in sorted(TASKS):
            print(task)
        return 0
    if args.task:
        return execute(args.task)

    try:
        tasks = manifest_tasks()
    except ValueError as exc:
        return fail(str(exc))
    for task in tasks:
        result = execute(task)
        if result:
            return result
    print("Product Validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
