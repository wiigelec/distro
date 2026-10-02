#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import pwd
import shutil
import subprocess
import tarfile
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "bootstrap-13.1.json"
USER_AGENT = "distro-lfs-bootstrap/0"
LFS_SOURCE_MIRROR = "https://ftp.osuosl.org/pub/lfs/lfs-packages/13.1/"


def require_root() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("bootstrap fixture creation must run as root")


def require_x86_64() -> None:
    machine = platform.machine().lower()
    if machine not in {"x86_64", "amd64"}:
        raise RuntimeError(f"bootstrap fixture currently supports x86_64 only, got {machine}")


def run(argv: list[str], *, cwd: Path | None = None,
        env: dict[str, str] | None = None,
        stdout=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, cwd=cwd, env=env, stdout=stdout,
        stderr=subprocess.STDOUT if stdout is not None else None,
        text=True, check=True,
    )


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_md5: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and md5_file(destination) == expected_md5:
        return destination
    destination.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        with destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    actual = md5_file(destination)
    if actual != expected_md5:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"checksum mismatch for {url}: {actual} != {expected_md5}")
    return destination


def top_directory(archive: Path) -> str:
    with tarfile.open(archive, "r:*") as tar:
        roots = {
            Path(member.name).parts[0]
            for member in tar.getmembers()
            if member.name and Path(member.name).parts
        }
    if len(roots) != 1:
        raise RuntimeError(f"{archive}: expected one archive root, found {sorted(roots)}")
    return next(iter(roots))


def builder_identity(requested: str | None) -> tuple[str, int, int]:
    name = requested or os.environ.get("SUDO_USER")
    if not name or name == "root":
        raise RuntimeError(
            "bootstrap needs an unprivileged host builder; run with sudo from that "
            "account or pass --builder-user"
        )
    record = pwd.getpwnam(name)
    return name, record.pw_uid, record.pw_gid


def builder_env(root: Path, uid: int, jobs: int) -> dict[str, str]:
    home = pwd.getpwuid(uid).pw_dir
    target = f"{platform.machine()}-lfs-linux-gnu"
    return {
        "HOME": home,
        "TERM": os.environ.get("TERM", "dumb"),
        "PS1": r"\u:\w\$ ",
        "PATH": f"{root}/tools/bin:/usr/bin:/bin",
        "LFS": str(root),
        "LC_ALL": "POSIX",
        "LFS_TGT": target,
        "CONFIG_SITE": f"{root}/usr/share/config.site",
        "MAKEFLAGS": f"-j{jobs}",
    }


def run_as_builder(user: str, script: str, *, cwd: Path,
                   env: dict[str, str], log) -> None:
    argv = ["runuser", "-u", user, "--", "env", "-i"]
    argv.extend(f"{key}={value}" for key, value in env.items())
    argv.extend(["/bin/bash", "-e", "-o", "pipefail", "-c", script])
    log.write(f"\n# host-builder cwd={cwd}\n{script}\n")
    log.flush()
    run(argv, cwd=cwd, stdout=log)


def run_in_chroot(root: Path, script: str, *, cwd: str, jobs: int, log) -> None:
    shell = f"cd {cwd!s} && {script}"
    argv = [
        "chroot", str(root),
        "/usr/bin/env", "-i",
        "HOME=/root",
        f"TERM={os.environ.get('TERM', 'dumb')}",
        "PATH=/usr/bin:/usr/sbin",
        f"MAKEFLAGS=-j{jobs}",
        f"TESTSUITEFLAGS=-j{jobs}",
        "/bin/bash", "-e", "-o", "pipefail", "-c", shell,
    ]
    log.write(f"\n# chroot-root cwd={cwd}\n{script}\n")
    log.flush()
    run(argv, stdout=log)


def mount(argv: list[str]) -> None:
    subprocess.run(argv, check=True)


@contextmanager
def kernel_filesystems(root: Path):
    mounted: list[Path] = []
    try:
        for relative in ("dev", "proc", "sys", "run"):
            (root / relative).mkdir(parents=True, exist_ok=True)

        mount(["mount", "--bind", "/dev", str(root / "dev")])
        mounted.append(root / "dev")
        mount(["mount", "-t", "devpts", "devpts", "-o", "gid=5,mode=0620",
               str(root / "dev/pts")])
        mounted.append(root / "dev/pts")
        mount(["mount", "-t", "proc", "proc", str(root / "proc")])
        mounted.append(root / "proc")
        mount(["mount", "-t", "sysfs", "sysfs", str(root / "sys")])
        mounted.append(root / "sys")
        mount(["mount", "-t", "tmpfs", "tmpfs", str(root / "run")])
        mounted.append(root / "run")

        shm = root / "dev/shm"
        if shm.is_symlink():
            target = os.path.realpath(shm)
            # os.path.realpath resolves through the host path; use the link text instead.
            link = os.readlink(shm)
            target = root / link.lstrip("/")
            target.mkdir(parents=True, exist_ok=True)
        else:
            shm.mkdir(parents=True, exist_ok=True)
            mount(["mount", "-t", "tmpfs", "tmpfs", "-o", "nosuid,nodev", str(shm)])
            mounted.append(shm)
        yield
    finally:
        for target in reversed(mounted):
            subprocess.run(["umount", "-l", str(target)], check=False)


def initial_layout(root: Path, uid: int, gid: int) -> None:
    for relative in ("etc", "var", "usr/bin", "usr/lib", "usr/sbin", "tools", "sources"):
        (root / relative).mkdir(parents=True, exist_ok=True)

    for name in ("bin", "lib", "sbin"):
        link = root / name
        if not link.exists():
            link.symlink_to(f"usr/{name}")
    (root / "lib64").mkdir(exist_ok=True)

    os.chmod(root / "sources", 0o1777)
    for relative in ("etc", "var", "usr", "tools", "lib64", "sources"):
        subprocess.run(["chown", "-R", f"{uid}:{gid}", str(root / relative)], check=True)


def copy_source_inputs(plan: dict[str, Any], root: Path, cache: Path) -> dict[str, Path]:
    sources_dir = root / "sources"
    archives: dict[str, Path] = {}
    for key, item in plan["sources"].items():
        filename = item["filename"]
        cached = download(
            LFS_SOURCE_MIRROR + filename,
            cache / "bootstrap-sources" / filename,
            item["md5"],
        )
        destination = sources_dir / filename
        if not destination.exists():
            shutil.copy2(cached, destination)
        archives[key] = destination
        for resource in item.get("resources", {}).values():
            rname = resource["filename"]
            rcached = download(
                LFS_SOURCE_MIRROR + rname,
                cache / "bootstrap-sources" / rname,
                resource["md5"]
            )
            rdest = sources_dir / rname
            if not rdest.exists():
                shutil.copy2(rcached, rdest)
    return archives


def extract_for_stage(archive: Path, sources: Path, *,
                      user: str | None, env: dict[str, str] | None, log) -> Path:
    dirname = top_directory(archive)
    source = sources / dirname
    if source.exists():
        shutil.rmtree(source)
    script = f"tar -xf {archive.name}"
    if user is None:
        run(["/bin/bash", "-e", "-c", script], cwd=sources, stdout=log)
    else:
        assert env is not None
        run_as_builder(user, script, cwd=sources, env=env, log=log)
    if not source.is_dir():
        raise RuntimeError(f"{archive}: extraction did not create {source}")
    return source


def build_fixture(output: Path, cache: Path, builder_user: str | None = None) -> dict[str, Any]:
    require_root()
    require_x86_64()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    user, uid, gid = builder_identity(builder_user)
    jobs = int(subprocess.check_output(["nproc"], text=True).strip())
    if jobs < 1:
        raise RuntimeError(f"nproc returned invalid job count: {jobs}")

    output = output.resolve()
    cache = cache.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    initial_layout(output, uid, gid)
    archives = copy_source_inputs(plan, output, cache)
    env = builder_env(output, uid, jobs)
    log_path = cache / "bootstrap-build.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    stages = plan["stages"]
    host_stages = [stage for stage in stages if stage["context"] == "host-builder"]
    chroot_stages = [stage for stage in stages if stage["context"] == "chroot-root"]

    with log_path.open("w", encoding="utf-8") as log:
        for stage in host_stages:
            source = extract_for_stage(
                archives[stage["package"]], output / "sources",
                user=user, env=env, log=log,
            )
            try:
                script = "\n\n".join(stage["commands"])
                run_as_builder(user, script, cwd=source, env=env, log=log)
            finally:
                shutil.rmtree(source, ignore_errors=True)

        # Chapter 7 handoff: ownership and virtual filesystems.
        for relative in ("usr", "var", "etc", "tools", "lib64"):
            subprocess.run(
                ["chown", "-R", "root:root", str(output / relative)], check=True
            )

        with kernel_filesystems(output):
            for command in plan["chroot_setup"]:
                run_in_chroot(output, command, cwd="/", jobs=jobs, log=log)

            for stage in chroot_stages:
                source = extract_for_stage(
                    archives[stage["package"]], output / "sources",
                    user=None, env=None, log=log,
                )
                source_inside = "/" + str(source.relative_to(output))
                try:
                    script = "\n\n".join(stage["commands"])
                    run_in_chroot(
                        output, script, cwd=source_inside, jobs=jobs, log=log
                    )
                finally:
                    shutil.rmtree(source, ignore_errors=True)

            for command in plan["cleanup"]:
                run_in_chroot(output, command, cwd="/", jobs=jobs, log=log)

    required = [
        "usr/bin/bash",
        "usr/bin/gcc",
        "usr/bin/g++",
        "usr/bin/ld",
        "usr/bin/make",
        "usr/bin/python3",
        "usr/lib/libc.so.6",
        "usr/lib/ld-linux-x86-64.so.2",
        "etc/passwd",
        "etc/group",
    ]
    missing = [item for item in required if not os.path.lexists(output / item)]
    if missing:
        raise RuntimeError(f"LFS handoff fixture missing required paths: {missing}")

    probe = subprocess.run(
        ["chroot", str(output), "/usr/bin/env", "-i",
         "PATH=/usr/bin:/usr/sbin", "/bin/bash", "-c",
         "gcc --version >/dev/null && python3 --version >/dev/null && /bin/bash --version >/dev/null"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if probe.returncode != 0:
        raise RuntimeError("LFS handoff fixture failed chroot tool probe")

    result = {
        "schema_version": 1,
        "status": "success",
        "kind": "lfs-chroot-handoff-fixture",
        "basis": plan["basis"],
        "root": str(output),
        "builder_user": user,
        "jobs": jobs,
        "bootstrap_stages": [stage["id"] for stage in stages],
        "build_log": str(log_path),
    }
    (output / "fixture-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="build the LFS Chapter 5-7 chroot handoff fixture"
    )
    parser.add_argument("--output", type=Path, default=Path("/tmp/lfs-chroot-fixture"))
    parser.add_argument("--cache", type=Path, default=Path("/tmp/lfs-optimize-cache"))
    parser.add_argument("--builder-user")
    args = parser.parse_args()
    result = build_fixture(args.output, args.cache, args.builder_user)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
