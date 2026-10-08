#!/usr/bin/env python3
"""Validate only prototype document structure, NOT package closure or runtime functionality."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
caps = json.loads((ROOT / "capabilities.json").read_text())
manifest = json.loads((ROOT / "build-chroot-candidate.json").read_text())
assert caps["status"] == "exploratory"
assert manifest["proven"] is False
assert manifest["status"] == "hypothesis-not-dependency-closed"
assert len({x["id"] for x in caps["baseline_capabilities"]}) == len(caps["baseline_capabilities"])
assert len({x["name"] for x in manifest["selected_for_experiment_only"]}) == len(manifest["selected_for_experiment_only"])
assert manifest["unresolved"]
print("PASS: prototype schema/invariant smoke check only; no builds or runtime tests performed")
