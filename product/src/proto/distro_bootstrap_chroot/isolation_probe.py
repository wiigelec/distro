#!/usr/bin/env python3
"""B0: bounded, nonprivileged Bubblewrap observation; no fallback to sudo/chroot."""
import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path


def run(argv, timeout=90):
    try:
        r = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
        return {"returncode": r.returncode, "stdout": r.stdout[-3000:], "stderr": r.stderr[-3000:]}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": type(e).__name__, "message": str(e)[:500]}


def main():
    ap = argparse.ArgumentParser(description="Observe Bubblewrap isolation for Distro B0")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    record = {"schema_version": 1, "stage": "B0-isolation", "status": "blocked", "backend": "bubblewrap", "host": {"system": platform.system(), "machine": platform.machine(), "euid": os.geteuid()}, "limitations": ["Uses host tools/libraries read-only; not a Distro native toolchain", "Does not prove toolchain/sysroot hermeticity or minimum supported host versions"]}
    bwrap = shutil.which("bwrap")
    if not bwrap:
        record["reason"] = "bwrap missing"
    elif os.geteuid() == 0:
        record["reason"] = "run as unprivileged user, not root"
    else:
        with tempfile.TemporaryDirectory(prefix="distro-b0-isolation-") as td:
            base = Path(td)
            work = base / "work"
            work.mkdir()
            (base / "host-only-marker").write_text("must-not-be-visible\n")
            guest = r'''import json, os, subprocess
from pathlib import Path
result = {"uid": os.getuid(), "pid": os.getpid(), "cwd": os.getcwd(), "host_marker_visible": Path("/tmp/host-only-marker").exists(), "outside_work_visible": Path("/tmp/distro-b0-host-only-probe").exists(), "mount_namespace": os.readlink("/proc/self/ns/mnt"), "pid_namespace": os.readlink("/proc/self/ns/pid"), "network_namespace": os.readlink("/proc/self/ns/net")}
result["write_to_usr_denied"] = False
try:
    Path("/usr/distro-b0-must-not-write").write_text("oops")
except (OSError, PermissionError):
    result["write_to_usr_denied"] = True
for lang, command, suffix in (("c", "cc", "c"), ("cxx", "c++", "cc")):
    source = Path("/work/probe." + suffix)
    source.write_text("int main(void){return 0;}\\n".replace("\\n", "\n"))
    exe = Path("/work/a-" + lang)
    compile = subprocess.run([command, str(source), "-o", str(exe)], capture_output=True, text=True)
    check = {"compiled": compile.returncode == 0, "compiler_stderr": compile.stderr[-800:]}
    if compile.returncode == 0:
        execute = subprocess.run([str(exe)], capture_output=True, text=True)
        check["executed"] = execute.returncode == 0
    result[lang] = check
Path("/work/guest-result.json").write_text(json.dumps(result, indent=2))
'''
            (work / "guest.py").write_text(guest)
            cmd = [bwrap, "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-net", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/run", "--bind", str(work), "/work", "--chdir", "/work", "--setenv", "HOME", "/work", "--setenv", "TMPDIR", "/tmp", "--setenv", "PATH", "/usr/bin:/bin"]
            # Mount only tool/runtime directories; bind sources read-only and never expose the host root.
            for name in ("usr", "bin", "sbin", "lib", "lib64", "etc"):
                p = Path("/") / name
                if p.exists():
                    cmd += ["--ro-bind", str(p), str(p)]
            cmd += ["--", "/usr/bin/python3", "/work/guest.py"]
            record["mounts"] = ["/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc", "/work (writable)", "/tmp (private tmpfs)", "/proc (private)", "/dev (synthetic)"]
            record["execution"] = run(cmd)
            result_path = work / "guest-result.json"
            if result_path.exists():
                evidence = json.loads(result_path.read_text())
                record["guest"] = evidence
                gates = {"process_namespace": evidence.get("pid") == 1, "filesystem_privacy": not evidence.get("host_marker_visible") and not evidence.get("outside_work_visible"), "readonly_system": evidence.get("write_to_usr_denied") is True, "c_compile_run": evidence.get("c", {}).get("compiled") and evidence.get("c", {}).get("executed"), "cxx_compile_run": evidence.get("cxx", {}).get("compiled") and evidence.get("cxx", {}).get("executed")}
                record["gates"] = gates
                record["status"] = "provisional-pass" if record["execution"].get("returncode") == 0 and all(gates.values()) else "blocked"
            else:
                record["reason"] = "Bubblewrap did not write guest result; examine stderr; do not substitute privileged execution"
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload)
    else:
        print(payload, end="")
    return 0 if record["status"] == "provisional-pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
