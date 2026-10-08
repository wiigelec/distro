#!/usr/bin/env python3
"""B0 host observation. No privilege escalation, networking, or repo mutations."""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "host-contract.json"


def run(argv, timeout=15):
    try:
        p = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout, check=False)
        return {"returncode": p.returncode, "stdout": p.stdout[:1200], "stderr": p.stderr[:700]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": type(exc).__name__, "message": str(exc)[:300]}


def tool_record(name):
    found = shutil.which(name)
    if not found:
        return {"found": False}
    resolved = str(Path(found).resolve())
    version_args = {
        "cc": ["--version"], "c++": ["--version"], "as": ["--version"],
        "ld": ["--version"], "ar": ["--version"], "ranlib": ["--version"],
        "sh": [], "mount": ["--version"], "umount": ["--version"],
        "chroot": ["--version"], "bwrap": ["--version"], "unshare": ["--version"]
    }
    args = version_args.get(name, ["--version"])
    info = {"found": True, "path": found, "resolved_path": resolved}
    if args:
        observation = run([found, *args])
        lines = (observation.get("stdout", "") or observation.get("stderr", "")).splitlines()
        info["version_banner"] = lines[0][:240] if lines else None
        info["version_probe_returncode"] = observation.get("returncode")
    return info


def compile_probe(cc, cxx):
    if not cc or not cxx:
        return {"status": "blocked", "reason": "C or C++ compiler not found"}
    with tempfile.TemporaryDirectory(prefix="distro-b0-") as tmp:
        root = Path(tmp)
        result = {}
        for language, command, suffix in (("c", cc, "c"), ("cxx", cxx, "cc")):
            src = root / ("check." + suffix)
            binary = root / ("check-" + language)
            src.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            compiled = run([command, str(src), "-o", str(binary)], timeout=60)
            outcome = {"compile": compiled, "compile_ok": compiled.get("returncode") == 0}
            if outcome["compile_ok"]:
                outcome["execute"] = run([str(binary)])
                outcome["execute_ok"] = outcome["execute"].get("returncode") == 0
                if shutil.which("readelf"):
                    outcome["elf_interpreter"] = run(["readelf", "-l", str(binary)])
                    outcome["elf_dynamic"] = run(["readelf", "-d", str(binary)])
            result[language] = outcome
        return {"status": "success" if all(v.get("execute_ok") for v in result.values()) else "failed", "languages": result}


def main():
    parser = argparse.ArgumentParser(description="Inspect B0 foreign-host bootstrap prerequisites")
    parser.add_argument("--out", type=Path, help="Write JSON report to specified path; otherwise stdout")
    args = parser.parse_args()
    contract_bytes = CONTRACT.read_bytes()
    contract = json.loads(contract_bytes)
    names = list(dict.fromkeys(contract["required_commands"] + contract["observed_optional_commands"]))
    tools = {name: tool_record(name) for name in names}
    env_names = ["PATH", "CC", "CXX", "LD", "AR", "AS", "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR", "LD_LIBRARY_PATH", "LIBRARY_PATH", "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "CONFIG_SITE", "MAKEFLAGS"]
    environment = {key: {"present": key in os.environ, "value": os.environ.get(key) if key == "PATH" else None} for key in env_names}
    missing = [name for name in contract["required_commands"] if not tools[name]["found"]]
    compiler = compile_probe(tools["cc"].get("path"), tools["c++"].get("path"))
    issues = []
    if missing:
        issues.append("missing required command(s): " + ", ".join(missing))
    if compiler["status"] != "success":
        issues.append("host C/C++ compile/execute probe failed")
    if any(environment[key]["present"] for key in env_names[1:] if key not in ("MAKEFLAGS",)):
        issues.append("non-default build environment variables present; evaluate for contamination")
    result = {
        "schema_version": 1, "stage": "B0", "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "status": "provisional-pass" if not missing and compiler["status"] == "success" else "blocked",
        "host": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(),
                 "python": platform.python_version(), "euid": os.geteuid() if hasattr(os, "geteuid") else None},
        "target_hypothesis": contract["target"], "commands": tools,
        "environment": environment, "compile_probe": compiler,
        "missing_required_commands": missing, "observations_requiring_review": issues,
        "not_proven": ["isolation", "sysroot cleanliness", "version compatibility", "chroot execution", "target bootstrap"]
    }
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if result["status"] == "provisional-pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
