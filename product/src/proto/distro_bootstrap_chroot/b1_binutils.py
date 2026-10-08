#!/usr/bin/env python3
"""B1.1: independent pinned-source binutils proof; no privileged operations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / "b1-binutils-source.json").read_text())


def command(argv, *, cwd=None, timeout=1800, stdout=None):
    try:
        proc = subprocess.run(argv, cwd=cwd, text=True, stdout=stdout or subprocess.PIPE,
                              stderr=subprocess.STDOUT if stdout else subprocess.PIPE,
                              timeout=timeout, check=False)
        return {"returncode": proc.returncode, "stdout": (proc.stdout or "")[-1000:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": type(exc).__name__, "message": str(exc)[:300]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--workspace", type=Path, help="Preserve source/build/prefix/logs; must be absent or empty")
    args = ap.parse_args()
    report = {"schema_version": 1, "stage": "B1-binutils", "status": "blocked", "source": LOCK,
              "limitations": ["host compiler and libraries still used", "no target libc/GCC or true sysroot", "upstream checksum file not signature-verified"]}
    if os.geteuid() == 0:
        report["reason"] = "must run unprivileged"
    elif not shutil.which("bwrap"):
        report["reason"] = "bwrap unavailable"
    else:
        workspace = args.workspace.resolve() if args.workspace else None
        if workspace and workspace.exists() and any(workspace.iterdir()):
            report["reason"] = "workspace is nonempty; refusing to overwrite"
        else:
            temp = tempfile.TemporaryDirectory(prefix="distro-b1-binutils-") if not workspace else None
            try:
                base = workspace if workspace else Path(temp.name)
                base.mkdir(parents=True, exist_ok=True)
                archive = base / LOCK["archive"]
                try:
                    with urllib.request.urlopen(LOCK["source_url"], timeout=90) as upstream, archive.open("wb") as dest:
                        shutil.copyfileobj(upstream, dest)
                    with archive.open("rb") as fp:
                        actual = hashlib.file_digest(fp, "sha512").hexdigest()
                    report["actual_sha512"] = actual
                    if actual != LOCK["sha512"]:
                        report["reason"] = "source digest mismatch"; return finish(report, args.out)
                    # Extraction must not write outside our workspace.
                    with tarfile.open(archive, "r:xz") as tar:
                        tar.extractall(base / "src", filter="data")
                    source = base / "src" / ("binutils-" + LOCK["version"])
                    if not (source / "configure").is_file():
                        report["reason"] = "configure missing"; return finish(report, args.out)
                except Exception as exc:
                    report["reason"] = "source acquisition/extraction failed: " + str(exc)[:300]
                    return finish(report, args.out)
                build = base / "build";build.mkdir()
                prefix = base / "prefix";prefix.mkdir()
                logs = base / "logs";logs.mkdir()
                # Resolve symlinks to avoid binding an overmounted /bin or /lib path accidentally.
                cmd = [shutil.which("bwrap"), "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-net", "--unshare-ipc", "--unshare-uts", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/run", "--bind", str(base), "/work", "--chdir", "/work/build", "--clearenv", "--setenv", "HOME", "/work", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LC_ALL", "C", "--setenv", "TMPDIR", "/tmp"]
                for name in ("usr", "bin", "sbin", "lib", "lib64", "etc"):
                    if (Path("/") / name).exists():
                        cmd += ["--ro-bind", "/" + name, "/" + name]
                script = """set -eu
/work/src/binutils-2.47/configure --target=x86_64-unknown-linux-gnu --prefix=/work/prefix --disable-nls --disable-werror --disable-gdb --disable-gprofng --disable-sim
make -j2
make install
/work/prefix/bin/x86_64-unknown-linux-gnu-as --version
/work/prefix/bin/x86_64-unknown-linux-gnu-ld --version
printf '.globl distro_b1_symbol\\ndistro_b1_symbol: nop\\n' > /work/check.s
/work/prefix/bin/x86_64-unknown-linux-gnu-as -o /work/check.o /work/check.s
/work/prefix/bin/x86_64-unknown-linux-gnu-ld -r -o /work/check-reloc.o /work/check.o
/usr/bin/readelf -h /work/check-reloc.o
"""
                (base / "build.sh").write_text(script)
                cmd += ["--", "/bin/sh", "/work/build.sh"]
                with (logs / "build.log").open("w") as f:
                    result = command(cmd, timeout=7200, stdout=f)
                report["execution"] = result
                report["log"] = str(logs / "build.log") if workspace else "temporary workspace log discarded"
                obj = base / "check-reloc.o"
                report["gates"] = {"digest_verified": actual == LOCK["sha512"],
                                   "build_exit_zero": result.get("returncode") == 0,
                                   "relocatable_object": obj.is_file(),
                                   "prefixed_assembler": (prefix / "bin/x86_64-unknown-linux-gnu-as").is_file(),
                                   "prefixed_linker": (prefix / "bin/x86_64-unknown-linux-gnu-ld").is_file()}
                report["status"] = "provisional-pass" if all(report["gates"].values()) else "blocked"
                if report["status"] != "provisional-pass":
                    report["reason"] = "see execution and build log; use --workspace to retain diagnostics"
            finally:
                if temp:
                    temp.cleanup()
    return finish(report, args.out)


def finish(record, destination):
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload)
    else:
        sys.stdout.write(payload)
    return 0 if record["status"] == "provisional-pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
