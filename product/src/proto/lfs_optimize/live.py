#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from artifact import (
    IGNORED_TOP_LEVEL,
    _record,
    create_tar_xz,
    extract_tar_xz,
    delta,
    materialize_delta,
    sha256_file,
    snapshot,
    snapshot_digest,
)
from execute import (
    CACHE_SCHEMA_VERSION,
    canonical_sha256,
    effective_jobs,
    prepare_sources,
    resolve_working_directory,
)

LIVE_EXCLUDED_PREFIXES = (
    "opt/distro-lfs-optimize",
    "var/cache/distro-lfs-optimize",
    "var/lib/distro-m8",
)


def _excluded(relative: str) -> bool:
    if not relative:
        return False
    parts = Path(relative).parts
    if parts and parts[0] in IGNORED_TOP_LEVEL:
        return True
    if parts[:2] == ("tmp", "distro-lfs-optimize"):
        return True
    return any(
        relative == prefix or relative.startswith(prefix + "/")
        for prefix in LIVE_EXCLUDED_PREFIXES
    )


def live_snapshot(root: Path) -> dict[str, dict[str, Any]]:
    root = root.resolve()
    paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        base = Path(dirpath)
        kept_dirs = []
        for name in sorted(dirnames):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if _excluded(relative):
                continue
            paths.append(path)
            if not path.is_symlink():
                kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if not _excluded(relative):
                paths.append(path)

    result: dict[str, dict[str, Any]] = {}
    hardlinks: dict[tuple[int, int], str] = {}
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        record = _record(path)
        if record["type"] == "file":
            st = path.lstat()
            if st.st_nlink > 1:
                key = (st.st_dev, st.st_ino)
                first = hardlinks.get(key)
                if first is None:
                    hardlinks[key] = relative
                else:
                    record["hardlink_to"] = first
        result[relative] = record
    return result


def report_cache_miss(
    package: dict[str, Any],
    cache: Path,
    cache_key: str,
    base_digest: str,
    definition_digest: str,
    jobs: int,
    before: dict[str, dict[str, Any]],
    notify: Callable[[str], None],
) -> None:
    label = f"{package['name']} {package['version']}"
    evidence_dir = cache / "evidence"
    pattern = f"{package['name']}-{package['version']}-*.json"
    candidates = (
        sorted(
            evidence_dir.glob(pattern),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if evidence_dir.is_dir()
        else []
    )

    notify(
        f"{label}: cache-debug expected-key={cache_key[:16]} "
        f"baseline={base_digest[:16]} definition={definition_digest[:16]} jobs={jobs}"
    )

    debug_dir = evidence_dir / ".baseline-debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_path = debug_dir / f"{package['name']}-{package['version']}.json"
    previous_snapshot = None
    if debug_path.is_file():
        try:
            previous_payload = json.loads(debug_path.read_text(encoding="utf-8"))
            if isinstance(previous_payload, dict) and isinstance(
                previous_payload.get("snapshot"), dict
            ):
                previous_snapshot = previous_payload["snapshot"]
        except (OSError, json.JSONDecodeError):
            previous_snapshot = None

    if previous_snapshot is None:
        notify(f"{label}: cache-debug baseline-diff=seeded")
    else:
        previous_paths = set(previous_snapshot)
        current_paths = set(before)
        added = sorted(current_paths - previous_paths)
        removed = sorted(previous_paths - current_paths)
        changed = sorted(
            path
            for path in previous_paths & current_paths
            if previous_snapshot[path] != before[path]
        )
        notify(
            f"{label}: cache-debug baseline-diff "
            f"added={len(added)} removed={len(removed)} changed={len(changed)}"
        )
        differences = (
            [("added", path) for path in added]
            + [("removed", path) for path in removed]
            + [("changed", path) for path in changed]
        )
        for kind, path in differences[:40]:
            notify(f"{label}: cache-debug baseline-{kind} {path}")
        if len(differences) > 40:
            notify(
                f"{label}: cache-debug baseline-diff-truncated "
                f"remaining={len(differences) - 40}"
            )

    debug_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "package": package["name"],
                "version": package["version"],
                "baseline_root_sha256": base_digest,
                "snapshot": before,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    if not candidates:
        notify(f"{label}: cache-debug candidates=0")
        return

    notify(
        f"{label}: cache-debug candidates={len(candidates)} "
        f"showing={min(5, len(candidates))}"
    )
    for candidate_path in candidates[:5]:
        try:
            evidence = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            notify(
                f"{label}: cache-debug candidate={candidate_path.name} "
                f"unreadable={type(exc).__name__}"
            )
            continue

        candidate_key = evidence.get("cache_key")
        candidate_artifact = (
            cache
            / "artifacts"
            / f"{package['name']}-{package['version']}-{candidate_key}.tar.xz"
            if isinstance(candidate_key, str) and candidate_key
            else None
        )
        artifact_exists = bool(candidate_artifact and candidate_artifact.is_file())
        artifact_sha_ok = False
        if artifact_exists:
            expected_artifact_sha = evidence.get("artifact_sha256")
            artifact_sha_ok = (
                isinstance(expected_artifact_sha, str)
                and expected_artifact_sha == sha256_file(candidate_artifact)
            )

        notify(
            f"{label}: cache-debug candidate-key={str(candidate_key)[:16]} "
            f"status={evidence.get('status')} "
            f"mode={evidence.get('execution_mode')} "
            f"baseline={'match' if evidence.get('baseline_root_sha256') == base_digest else 'DIFF'} "
            f"definition={'match' if evidence.get('resolved_package_sha256') == definition_digest else 'DIFF'} "
            f"jobs={'match' if evidence.get('jobs') == jobs else 'DIFF'} "
            f"artifact={'ok' if artifact_exists and artifact_sha_ok else 'missing-or-bad'}"
        )

def live_command(
    command: dict[str, Any], cwd: str, log, index: int, jobs: int
) -> dict[str, Any]:
    user = command["user"]
    env = {
        "HOME": "/root" if user == "root" else f"/home/{user}",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "MAKEFLAGS": f"-j{jobs}",
    }
    env.update(command.get("environment", {}))
    shell = f"cd {shlex.quote(cwd)} && {command['command']}"
    argv: list[str] = []
    if user != "root":
        argv.extend(["runuser", "-u", user, "--"])
    argv.extend(["/usr/bin/env", "-i"])
    argv.extend(f"{key}={value}" for key, value in env.items())
    argv.extend(["/bin/bash", "-o", "pipefail", "-c", shell])

    log.write(
        f"\n# live command {index} user={user} kind={command.get('kind', 'command')}\n"
        f"$ {command['command']}\n"
    )
    log.flush()
    completed = subprocess.run(
        argv, stdout=log, stderr=subprocess.STDOUT, text=True
    )
    return {
        "index": index,
        "user": user,
        "command": command["command"],
        "source_command": command.get("source_command"),
        "exit_code": completed.returncode,
        "executed": True,
    }


def build_package_live(
    package: dict[str, Any],
    root: Path,
    work: Path,
    cache: Path,
    run_tests: bool,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise RuntimeError("live package execution requires root")
    root = root.resolve()
    if root != Path("/"):
        raise RuntimeError("live package execution currently requires root=/")
    if run_tests:
        raise RuntimeError(
            "live package execution does not yet isolate test-only mutations; use --skip-tests"
        )
    if Path("/proc/1/comm").read_text(encoding="utf-8").strip() != "systemd":
        raise RuntimeError("live package execution requires systemd as PID 1")

    jobs = effective_jobs()
    notify = progress or (lambda message: None)
    label = f"{package['name']} {package['version']}"
    notify(f"{label}: snapshot-before")
    before = live_snapshot(root)
    base_digest = snapshot_digest(before)
    definition_digest = canonical_sha256(package)
    cache_key = canonical_sha256(
        {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "execution_mode": "live",
            "resolved_package_sha256": definition_digest,
            "baseline_root_sha256": base_digest,
            "tests": False,
            "jobs": jobs,
        }
    )
    artifact = (
        cache
        / "artifacts"
        / f"{package['name']}-{package['version']}-{cache_key}.tar.xz"
    )
    evidence_path = (
        cache
        / "evidence"
        / f"{package['name']}-{package['version']}-{cache_key}.json"
    )
    package_work = work / package["name"]
    stage = package_work / "stage"
    log_path = package_work / "build.log"
    result_path = package_work / "result.json"
    package_work.mkdir(parents=True, exist_ok=True)

    if artifact.is_file() and evidence_path.is_file():
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if (
            evidence.get("status") == "success"
            and evidence.get("execution_mode") == "live"
            and evidence.get("cache_key") == cache_key
            and evidence.get("artifact_sha256") == sha256_file(artifact)
            and evidence.get("baseline_root_sha256") == base_digest
            and evidence.get("resolved_package_sha256") == definition_digest
        ):
            notify(f"{label}: cache-hit restore")
            extract_tar_xz(artifact, root)
            transition_results: list[dict[str, Any]] = []
            with log_path.open("w", encoding="utf-8") as log:
                index = 0
                for step in package["procedure"]:
                    if step["condition"] == "tests-enabled":
                        continue
                    for command in step["commands"]:
                        index += 1
                        if command.get("kind") != "session-transition":
                            continue
                        notify(f"{label}: {step['phase']} session-transition")
                        item = live_command(command, "/", log, index, jobs)
                        item["phase"] = step["phase"]
                        item["disposition"] = (
                            "executed-session-transition"
                            if item["exit_code"] == 0
                            else "fatal"
                        )
                        transition_results.append(item)
                        if item["exit_code"] != 0:
                            result = {
                                "schema_version": 1,
                                "status": "failure",
                                "execution_mode": "live",
                                "package": package["name"],
                                "version": package["version"],
                                "build": package.get("build", "default"),
                                "cache": "hit",
                                "cache_key": cache_key,
                                "artifact": str(artifact),
                                "artifact_sha256": sha256_file(artifact),
                                "baseline_root_sha256": base_digest,
                                "resolved_package_sha256": definition_digest,
                                "failed_command": item,
                                "jobs": jobs,
                                "tests_enabled": False,
                                "manual_checks": evidence.get("manual_checks", []),
                                "review_required": bool(evidence.get("manual_checks", [])),
                                "live_transitions": transition_results,
                            }
                            result_path.write_text(
                                json.dumps(result, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8",
                            )
                            return result

            notify(f"{label}: cache-hit verify")
            after = live_snapshot(root)
            final_digest = snapshot_digest(after)
            expected_final = evidence.get("final_root_sha256")
            if final_digest != expected_final:
                raise RuntimeError(
                    f"{package['name']}: cached live artifact realization mismatch: "
                    f"{final_digest} != {expected_final}"
                )
            result = {
                "schema_version": 1,
                "status": "success",
                "execution_mode": "live",
                "package": package["name"],
                "version": package["version"],
                "build": package.get("build", "default"),
                "cache": "hit",
                "cache_key": cache_key,
                "artifact": str(artifact),
                "artifact_sha256": sha256_file(artifact),
                "artifact_reused": True,
                "realization_verified": True,
                "baseline_root_sha256": base_digest,
                "final_root_sha256": final_digest,
                "resolved_package_sha256": definition_digest,
                "cache_schema_version": CACHE_SCHEMA_VERSION,
                "jobs": jobs,
                "tests_enabled": False,
                "test_status": evidence.get("test_status", "not-run"),
                "manual_checks": evidence.get("manual_checks", []),
                "review_required": bool(evidence.get("manual_checks", [])),
                "live_transitions": transition_results,
            }
            result_path.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            notify(f"{label}: complete cache=hit")
            return result

    notify(f"{label}: cache-miss")
    report_cache_miss(
        package,
        cache,
        cache_key,
        base_digest,
        definition_digest,
        jobs,
        before,
        notify,
    )
    source_cwd = prepare_sources(package, root, cache)
    command_results: list[dict[str, Any]] = []
    manual_checks: list[dict[str, Any]] = []

    with log_path.open("w", encoding="utf-8") as log:
        index = 0
        for step in package["procedure"]:
            if step["condition"] == "tests-enabled":
                continue
            step_cwd = resolve_working_directory(
                source_cwd, step["working_directory"]
            )
            for command in step["commands"]:
                index += 1
                kind = command.get("kind", "command")
                notify(f"{label}: {step['phase']} command={index}")
                if kind == "manual-check":
                    item = {
                        "index": index,
                        "user": command["user"],
                        "command": command["command"],
                        "source_command": command.get("source_command"),
                        "exit_code": 0,
                        "executed": False,
                        "disposition": "recorded-manual-check",
                    }
                    manual_checks.append(item.copy())
                else:
                    item = live_command(command, step_cwd, log, index, jobs)
                    if kind == "session-transition":
                        item["disposition"] = "executed-session-transition"
                item["phase"] = step["phase"]
                command_results.append(item)
                if item["exit_code"] != 0:
                    item["disposition"] = "fatal"
                    result = {
                        "schema_version": 1,
                        "status": "failure",
                        "execution_mode": "live",
                        "package": package["name"],
                        "version": package["version"],
                        "build": package.get("build", "default"),
                        "failed_command": item,
                        "commands": command_results,
                        "build_log": str(log_path),
                        "jobs": jobs,
                        "tests_enabled": False,
                        "manual_checks": manual_checks,
                        "review_required": bool(manual_checks),
                    }
                    result_path.write_text(
                        json.dumps(result, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    notify(f"{label}: failed phase={step['phase']} exit={item['exit_code']}")
                    return result

    notify(f"{label}: snapshot-after")
    after = live_snapshot(root)
    notify(f"{label}: delta")
    changed, deleted = delta(before, after)
    materialize_delta(root, stage, changed, after)

    notify(f"{label}: artifact")
    create_tar_xz(stage, artifact, deleted)
    shutil.rmtree(stage, ignore_errors=True)

    result = {
        "schema_version": 1,
        "status": "success",
        "execution_mode": "live",
        "package": package["name"],
        "version": package["version"],
        "build": package.get("build", "default"),
        "cache": "miss",
        "cache_key": cache_key,
        "artifact": str(artifact),
        "artifact_sha256": sha256_file(artifact),
        "baseline_root_sha256": base_digest,
        "final_root_sha256": snapshot_digest(after),
        "resolved_package_sha256": definition_digest,
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "jobs": jobs,
        "commands": command_results,
        "tests_enabled": False,
        "test_status": "not-run",
        "manual_checks": manual_checks,
        "review_required": bool(manual_checks),
        "live_transitions": [
            item
            for item in command_results
            if item.get("disposition") == "executed-session-transition"
        ],
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    notify(f"{label}: complete cache=miss")
    return result
