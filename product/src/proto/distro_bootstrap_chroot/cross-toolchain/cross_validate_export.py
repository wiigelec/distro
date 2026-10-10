#!/usr/bin/env python3
"""Gate cross-toolchain export on isolated compile/link/ELF/runtime checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

TARGET = "x86_64-unknown-linux-gnu"
INTERPRETER = "/lib64/ld-linux-x86-64.so.2"

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def check(cmd, **kwargs):
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=90, check=False, **kwargs)
    if p.returncode:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(map(str,cmd))}\n{p.stdout[-1500:]}\n{p.stderr[-2500:]}")
    return p

def elf_checks(object_file, executable):
    header = check(["readelf", "-h", str(object_file)]).stdout
    if "ELF64" not in header or "X86-64" not in header or "REL (Relocatable file)" not in header:
        raise RuntimeError("compile-only output is not a relocatable x86-64 ELF64 object")
    headers = check(["readelf", "-l", str(executable)]).stdout
    if f"[Requesting program interpreter: {INTERPRETER}]" not in headers:
        raise RuntimeError("unexpected executable ELF interpreter")
    dynamic = check(["readelf", "-d", str(executable)]).stdout
    needed = [line for line in dynamic.splitlines() if "(NEEDED)" in line]
    if len(needed) != 1 or "[libc.so.6]" not in needed[0]:
        raise RuntimeError(f"unexpected executable runtime dependencies: {needed}")
    return {"elf_class": "ELF64", "machine": "X86-64",
            "interpreter": INTERPRETER, "needed": ["libc.so.6"]}

def export(root, destination):
    # Archive paths relative to root; never dereference symbolic links.
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + ".tmp")
    try:
        with tarfile.open(tmp, "w:xz", dereference=False, format=tarfile.PAX_FORMAT) as tar:
            for current, dirs, files in os.walk(root, followlinks=False):
                current = Path(current)
                for name in sorted(dirs + files):
                    path = current / name
                    relative = path.relative_to(root)
                    if path.is_symlink():
                        target = os.readlink(path)
                        if Path(target).is_absolute():
                            raise RuntimeError(f"absolute archive symlink: {relative}")
                        parts = list(relative.parent.parts) if relative.parent != Path(".") else []
                        for part in Path(target).parts:
                            if part == "..":
                                if not parts:
                                    raise RuntimeError(f"escaping archive symlink: {relative}")
                                parts.pop()
                            elif part not in (".", ""):
                                parts.append(part)
                    info = tar.gettarinfo(str(path), arcname=relative.as_posix())
                    if not (info.isfile() or info.isdir() or info.issym()):
                        raise RuntimeError(f"unsupported root entry: {relative}")
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    if info.isfile():
                        with path.open("rb") as stream:
                            tar.addfile(info, stream)
                    else:
                        tar.addfile(info)
        os.replace(tmp, destination)
    finally:
        if tmp.exists():
            tmp.unlink()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--project", type=Path, required=True)
    args = p.parse_args()
    root = args.root.resolve()
    project = args.project.resolve()
    if root != project / "root" or root.is_symlink() or not root.is_dir():
        raise RuntimeError("invalid bootstrap root")
    gcc = root / "bin" / (TARGET + "-gcc")
    for item in (gcc, root / "lib64/libc.so.6",
                 root / "lib64/ld-linux-x86-64.so.2",
                 root / "usr/lib64/crt1.o", root / "usr/lib64/crti.o",
                 root / "usr/lib64/crtn.o"):
        if not item.is_file():
            raise RuntimeError(f"missing bootstrap prerequisite: {item}")
    if not shutil.which("bwrap") or not shutil.which("readelf"):
        raise RuntimeError("validation requires bubblewrap and readelf")
    work = project / ".distro-bootstrap/validation/cross-toolchain"
    work.mkdir(parents=True, exist_ok=True)
    src = work / "smoke.c"
    obj = work / "smoke.o"
    binary = work / "smoke"
    src.write_text('#include <stdio.h>\nint main(void) { puts("distro-cross-toolchain-ok"); return 0; }\n')
    # Mirror the working cross_runner sandbox. Binding host / read-only first
    # prevents Bubblewrap from creating /toolchain as a mount point.
    sandbox = ["bwrap", "--die-with-parent", "--new-session",
               "--unshare-user", "--unshare-pid", "--unshare-net",
               "--unshare-ipc", "--unshare-uts",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
               "--dir", "/run", "--ro-bind", str(root), "/toolchain",
               "--bind", str(work), "/work", "--clearenv",
               "--setenv", "HOME", "/work",
               "--setenv", "PATH", "/toolchain/bin:/usr/bin:/bin",
               "--setenv", "LC_ALL", "C"]
    for name in ("usr", "bin", "sbin", "lib", "lib64", "etc"):
        if (Path("/") / name).exists():
            sandbox.extend(["--ro-bind", "/" + name, "/" + name])
    sandbox.append("--")
    compiler = f"/toolchain/bin/{TARGET}-gcc"
    check(sandbox + [compiler, "--sysroot=/toolchain", "-fno-link-libatomic",
                     "-c", "/work/smoke.c", "-o", "/work/smoke.o"])
    print("[validate] compile-only: PASS", flush=True)
    check(sandbox + [compiler, "--sysroot=/toolchain", "-fno-link-libatomic",
                     "/work/smoke.c", "-o", "/work/smoke"])
    print("[validate] executable link: PASS", flush=True)
    elf = elf_checks(obj, binary)
    print("[validate] ELF interpreter and NEEDED: PASS", flush=True)
    runtime = check(sandbox + ["/toolchain/lib64/ld-linux-x86-64.so.2",
                       "--library-path", "/toolchain/lib64:/toolchain/usr/lib64",
                       "/work/smoke"])
    if runtime.stdout.strip() != "distro-cross-toolchain-ok":
        raise RuntimeError("unexpected smoke executable output")
    print("[validate] target-glibc runtime: PASS", flush=True)
    artifact = project / "artifacts/cross-toolchain-root.tar.xz"
    export(root, artifact)
    record = {"schema_version": 1, "phase": "cross-toolchain", "status": "passed",
              "target": TARGET, "elf": elf,
              "archive": str(artifact), "archive_sha256": sha256(artifact),
              "archive_bytes": artifact.stat().st_size}
    report = artifact.with_suffix(artifact.suffix + ".json")
    report.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(f"[export] {artifact}", flush=True)
    print(f"[export] sha256={record['archive_sha256']}", flush=True)

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"[validate] FAILED: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
