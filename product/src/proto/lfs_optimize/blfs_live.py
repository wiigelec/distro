#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

from artifact import snapshot_digest
from blfs import resolve_blfs
from live import build_package_live, live_snapshot


def systemd_version() -> str:
    completed = subprocess.run(
        ["systemctl", "--version"], check=True, capture_output=True, text=True
    )
    return completed.stdout.splitlines()[0]


def run_live_blfs(work: Path, cache: Path, run_tests: bool) -> dict[str, Any]:
    if Path("/proc/1/comm").read_text(encoding="utf-8").strip() != "systemd":
        raise RuntimeError("BLFS live proof requires systemd as PID 1")
    if run_tests:
        raise RuntimeError("BLFS live proof currently requires --skip-tests")

    resolved = resolve_blfs()
    work.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    result_path = work.parent / "result.json"
    initial_digest = snapshot_digest(live_snapshot(Path("/")))
    package_results: list[dict[str, Any]] = []

    for package in resolved["packages"]:
        result = build_package_live(
            package, Path("/"), work / "packages", cache, run_tests=False
        )
        package_results.append(result)
        if result["status"] != "success":
            payload = {
                "schema_version": 1,
                "status": "failure",
                "kind": "booted-blfs-live-proof",
                "package_set": resolved["package_set"],
                "version_manifest": resolved["version_manifest"],
                "kernel": platform.release(),
                "pid1": "systemd",
                "systemd": systemd_version(),
                "initial_root_sha256": initial_digest,
                "failed_package": package["name"],
                "packages": package_results,
                "review_required": any(
                    item.get("review_required") for item in package_results
                ),
            }
            result_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return payload

    payload = {
        "schema_version": 1,
        "status": "success",
        "kind": "booted-blfs-live-proof",
        "package_set": resolved["package_set"],
        "version_manifest": resolved["version_manifest"],
        "kernel": platform.release(),
        "pid1": "systemd",
        "systemd": systemd_version(),
        "initial_root_sha256": initial_digest,
        "final_root_sha256": snapshot_digest(live_snapshot(Path("/"))),
        "packages": package_results,
        "review_required": any(
            item.get("review_required") for item in package_results
        ),
        "manual_checks": [
            check
            for item in package_results
            for check in item.get("manual_checks", [])
        ],
        "live_transitions": [
            transition
            for item in package_results
            for transition in item.get("live_transitions", [])
        ],
    }
    result_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="execute the normalized M8 BLFS package set on a booted LFS guest"
    )
    parser.add_argument("--work", type=Path, default=Path("/var/lib/distro-m8/work"))
    parser.add_argument(
        "--cache", type=Path, default=Path("/var/cache/distro-lfs-optimize")
    )
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    result = run_live_blfs(args.work, args.cache, run_tests=not args.skip_tests)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
