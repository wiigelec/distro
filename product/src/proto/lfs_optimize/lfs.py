#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

from artifact import snapshot, snapshot_digest
from bootstrap import build_fixture
from system import build_system


def link_shared_sources(shared_cache: Path, proof_cache: Path) -> None:
    proof_cache.mkdir(parents=True, exist_ok=True)
    for name in ("sources", "bootstrap-sources"):
        shared = shared_cache / name
        shared.mkdir(parents=True, exist_ok=True)
        link = proof_cache / name

        if os.path.lexists(link):
            if link.is_symlink() and link.resolve() == shared.resolve():
                continue
            raise RuntimeError(
                f"{link}: M4 cache entry exists and is not the expected "
                f"shared-source link"
            )

        link.symlink_to(shared.resolve(), target_is_directory=True)


def write_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_full_lfs(
    work: Path,
    cache: Path,
    *,
    builder_user: str | None,
    run_tests: bool,
    fresh_artifacts: bool,
) -> dict[str, Any]:
    work = work.resolve()
    cache = cache.resolve()
    bootstrap_root = work / "bootstrap-root"
    normal_work = work / "normal"
    result_path = work / "result.json"
    proof_cache = cache / "m4-proof"

    link_shared_sources(cache, proof_cache)
    if fresh_artifacts:
        shutil.rmtree(proof_cache / "artifacts", ignore_errors=True)

    bootstrap_result = build_fixture(
        bootstrap_root,
        proof_cache,
        builder_user,
    )
    handoff_digest = snapshot_digest(snapshot(bootstrap_root))

    system_result = build_system(
        bootstrap_root,
        normal_work,
        proof_cache,
        run_tests,
    )

    package_results = system_result.get("packages", [])
    cache_hits = sum(
        1 for item in package_results if item.get("cache") == "hit"
    )
    cache_misses = sum(
        1 for item in package_results if item.get("cache") == "miss"
    )

    status = system_result["status"]
    if (
        status == "success"
        and system_result["initial_root_sha256"] != handoff_digest
    ):
        raise RuntimeError(
            "bootstrap handoff digest does not match normal-system "
            "initial root"
        )
    if fresh_artifacts and cache_hits:
        raise RuntimeError(
            f"fresh M4 proof unexpectedly reused {cache_hits} artifact(s)"
        )

    result = {
        "schema_version": 1,
        "status": status,
        "kind": "lfs-bootstrap-to-normal-proof",
        "bootstrap": bootstrap_result,
        "bootstrap_handoff_sha256": handoff_digest,
        "normal_system": system_result,
        "normal_cache_hits": cache_hits,
        "normal_cache_misses": cache_misses,
        "fresh_artifacts": fresh_artifacts,
    }
    if status == "success":
        result["final_root_sha256"] = system_result["final_root_sha256"]

    write_result(result_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="prove bootstrap-to-normal complete LFS execution"
    )
    parser.add_argument(
        "--work",
        type=Path,
        default=Path("/tmp/lfs-optimize-m4"),
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("/tmp/lfs-optimize-cache"),
    )
    parser.add_argument("--builder-user")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument(
        "--fresh-artifacts",
        action="store_true",
        help="discard only the private M4 artifact cache before the proof",
    )
    args = parser.parse_args()

    result = build_full_lfs(
        args.work,
        args.cache,
        builder_user=args.builder_user,
        run_tests=not args.skip_tests,
        fresh_artifacts=args.fresh_artifacts,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
