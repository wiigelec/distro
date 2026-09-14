#!/usr/bin/env python3
"""Run inside the package-owned closed build root."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path


MUSL_VERSION = "1.2.6"
BUSYBOX_VERSION = "1.37.0"
SYSTEM_VERSION = "0.2.0"
USER_AGENT = "distro-closed-build/0"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def architecture():
    machine = platform.machine().lower()
    if machine not in {"x86_64", "amd64"}:
        raise RuntimeError("closed prototype currently supports x86_64 only")
    return "x86_64"


def download(url, destination):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def payload_paths(stage):
    paths = []
    for path in sorted(stage.rglob("*")):
        st = path.lstat()
        if stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
            paths.append(path.relative_to(stage).as_posix())
    return paths


def add_tree(tar, stage):
    for path in sorted(stage.rglob("*")):
        relative = path.relative_to(stage).as_posix()
        st = path.lstat()
        info = tarfile.TarInfo(f"root/{relative}")
        info.mode = stat.S_IMODE(st.st_mode)
        info.uid = 0
        info.gid = 0
        info.mtime = 0

        if stat.S_ISLNK(st.st_mode):
            info.type = tarfile.SYMTYPE
            info.linkname = os.readlink(path)
            tar.addfile(info)
        elif stat.S_ISDIR(st.st_mode):
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
        elif stat.S_ISREG(st.st_mode):
            info.type = tarfile.REGTYPE
            info.size = st.st_size
            with path.open("rb") as handle:
                tar.addfile(info, handle)


def create_artifact(repository, name, version, stage, metadata_extra=None):
    identity = {
        "name": name,
        "version": version,
        "architecture": architecture(),
        "revision": "r1",
    }
    filename = f"{name}-{version}-{identity['architecture']}-r1.distro.tar.gz"
    artifact = repository / "packages" / filename
    owned_paths = payload_paths(stage)

    metadata = {
        "schema_version": 1,
        "prototype": True,
        "identity": identity,
        "closed_build": True,
    }
    if metadata_extra:
        metadata.update(metadata_extra)

    with tarfile.open(artifact, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        data = json.dumps(metadata, indent=2, sort_keys=True).encode() + b"\n"
        info = tarfile.TarInfo("metadata.json")
        info.mode = 0o644
        info.uid = 0
        info.gid = 0
        info.mtime = 0
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

        root_info = tarfile.TarInfo("root")
        root_info.type = tarfile.DIRTYPE
        root_info.mode = 0o755
        root_info.uid = 0
        root_info.gid = 0
        root_info.mtime = 0
        tar.addfile(root_info)
        add_tree(tar, stage)

    return {
        "identity": identity,
        "artifact": f"packages/{filename}",
        "artifact_sha256": sha256_file(artifact),
        "owned_paths": owned_paths,
    }


def empty_package(repository, name, version):
    with tempfile.TemporaryDirectory(prefix="distro-empty-") as temporary:
        return create_artifact(repository, name, version, Path(temporary))


def build_target_repository(output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "packages").mkdir()

    with tempfile.TemporaryDirectory(prefix="distro-closed-build-") as temporary:
        work = Path(temporary)
        musl_archive = work / f"musl-{MUSL_VERSION}.tar.gz"
        busybox_archive = work / f"busybox-{BUSYBOX_VERSION}.tar.bz2"

        download(
            f"https://musl.libc.org/releases/musl-{MUSL_VERSION}.tar.gz",
            musl_archive,
        )
        download(
            f"https://busybox.net/downloads/busybox-{BUSYBOX_VERSION}.tar.bz2",
            busybox_archive,
        )

        src = work / "src"
        src.mkdir()
        musl_stage = work / "musl-stage"
        busybox_stage = work / "busybox-stage"
        base_stage = work / "base-stage"
        kernel_stage = work / "kernel-stage"
        for stage in (musl_stage, busybox_stage, base_stage, kernel_stage):
            stage.mkdir()

        subprocess.run(
            ["tar", "-xzf", str(musl_archive), "-C", str(src)],
            check=True,
        )
        musl_src = src / f"musl-{MUSL_VERSION}"
        subprocess.run(
            ["./configure", "--prefix=/usr"],
            cwd=musl_src,
            check=True,
        )
        subprocess.run(["make", f"-j{os.cpu_count() or 1}"], cwd=musl_src, check=True)
        subprocess.run(
            ["make", f"DESTDIR={musl_stage}", "install"],
            cwd=musl_src,
            check=True,
        )

        # Arch's package-owned musl-gcc links against /usr/lib/ld-musl-*. The
        # target musl build provides the same loader through libc.so.
        loader = musl_stage / "usr/lib/ld-musl-x86_64.so.1"
        if not loader.exists():
            loader.parent.mkdir(parents=True, exist_ok=True)
            os.symlink("/usr/lib/libc.so", loader)

        subprocess.run(
            ["tar", "-xjf", str(busybox_archive), "-C", str(src)],
            check=True,
        )
        busybox_src = src / f"busybox-{BUSYBOX_VERSION}"
        subprocess.run(["make", "allnoconfig"], cwd=busybox_src, check=True)
        config = busybox_src / ".config"
        text = config.read_text()
        replacements = {
            "# CONFIG_LS is not set": "CONFIG_LS=y",
            "# CONFIG_ASH is not set": "CONFIG_ASH=y",
            "# CONFIG_SH_IS_ASH is not set": "CONFIG_SH_IS_ASH=y",
            "CONFIG_SH_IS_NONE=y": "# CONFIG_SH_IS_NONE is not set",
            "# CONFIG_INSTALL_APPLET_SYMLINKS is not set":
                "CONFIG_INSTALL_APPLET_SYMLINKS=y",
            "CONFIG_INSTALL_APPLET_DONT=y":
                "# CONFIG_INSTALL_APPLET_DONT is not set",
        }
        for before, after in replacements.items():
            text = text.replace(before, after)
        config.write_text(text)
        subprocess.run(
            ["/bin/bash", "-c", "yes '' | make oldconfig"],
            cwd=busybox_src,
            check=True,
        )
        subprocess.run(
            ["make", "CC=musl-gcc", f"-j{os.cpu_count() or 1}"],
            cwd=busybox_src,
            check=True,
        )
        subprocess.run(
            ["make", "CC=musl-gcc", f"CONFIG_PREFIX={busybox_stage}", "install"],
            cwd=busybox_src,
            check=True,
        )

        for directory in (
            "dev", "proc", "sys", "run", "tmp", "root", "mnt", "etc", "sbin"
        ):
            (base_stage / directory).mkdir(parents=True, exist_ok=True)
        (base_stage / "tmp").chmod(0o1777)
        (base_stage / "etc/profile").write_text(
            "PATH=/bin:/usr/bin\nexport PATH\n"
        )
        init = base_stage / "sbin/init"
        init.write_text("#!/bin/sh\nexec /bin/sh -l\n")
        init.chmod(0o755)

        kernel_image = Path("/boot/vmlinuz-linux")
        initramfs = Path("/boot/initramfs-linux.img")
        if not kernel_image.is_file() or not initramfs.is_file():
            raise RuntimeError(
                "bootstrap-tools must provide /boot/vmlinuz-linux and "
                "/boot/initramfs-linux.img"
            )
        (kernel_stage / "boot").mkdir(parents=True)
        shutil.copy2(kernel_image, kernel_stage / "boot/vmlinuz")
        shutil.copy2(initramfs, kernel_stage / "boot/initrd.img")

        musl = create_artifact(
            output, "musl", MUSL_VERSION, musl_stage,
            {"source_sha256": sha256_file(musl_archive)},
        )
        busybox = create_artifact(
            output, "busybox", BUSYBOX_VERSION, busybox_stage,
            {"source_sha256": sha256_file(busybox_archive)},
        )
        base_files = create_artifact(output, "base-files", "1.1.0", base_stage)
        kernel = create_artifact(
            output, "kernel", "bootstrap-linux", kernel_stage,
            {"source": "package:bootstrap-tools:/boot/vmlinuz-linux"},
        )
        system = empty_package(output, "system", SYSTEM_VERSION)

    database = {
        "schema_version": 1,
        "prototype": True,
        "architecture": architecture(),
        "closed_build": True,
        "packages": [
            {
                **musl,
                "depends": [],
                "conflicts": [],
                "provides": [{"name": "libc"}],
            },
            {
                **base_files,
                "depends": [],
                "conflicts": [],
                "provides": [],
            },
            {
                **kernel,
                "depends": [],
                "conflicts": [],
                "provides": [{"name": "kernel"}],
            },
            {
                **busybox,
                "depends": [{"name": "musl"}, {"name": "base-files"}],
                "conflicts": [],
                "provides": [],
            },
            {
                **system,
                "depends": [{"name": "busybox"}, {"name": "kernel"}],
                "conflicts": [],
                "provides": [{"name": "system"}],
            },
        ],
    }
    write_json(output / "database.json", database)
    return database


def copy_package_entry(source_repo, destination_repo, entry):
    source = source_repo / entry["artifact"]
    target = destination_repo / entry["artifact"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if sha256_file(target) != entry["artifact_sha256"]:
        raise RuntimeError(f"copied artifact checksum mismatch: {entry['artifact']}")
    return dict(entry)


def stage_installer_control(stage):
    (stage / "opt/distro").mkdir(parents=True, exist_ok=True)
    (stage / "usr/local/bin").mkdir(parents=True, exist_ok=True)

    shutil.copy2(
        "/opt/distro/proto/manager/manage.py",
        stage / "opt/distro/manage.py",
    )
    installer = stage / "usr/local/bin/install-distro"
    shutil.copy2(
        "/opt/distro/proto/install/install_distro.py",
        installer,
    )
    installer.chmod(0o755)

    init = stage / "init"
    init.write_text(
        "#!/bin/bash\n"
        "export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin\n"
        "export PS1='distro-installer# '\n"
        "mkdir -p /dev /proc /sys /run /tmp\n"
        "mount -t devtmpfs devtmpfs /dev 2>/dev/null || true\n"
        "mount -t proc proc /proc 2>/dev/null || true\n"
        "mount -t sysfs sysfs /sys 2>/dev/null || true\n"
        "mount -t tmpfs tmpfs /run 2>/dev/null || true\n"
        "modprobe virtio_pci 2>/dev/null || true\n"
        "modprobe virtio_blk 2>/dev/null || true\n"
        "modprobe ext4 2>/dev/null || true\n"
        "echo\n"
        "echo 'distro closed installer prototype'\n"
        "echo 'Install with: install-distro /dev/vda'\n"
        "echo\n"
        "exec /bin/bash --noprofile --norc\n"
    )
    init.chmod(0o755)


def stage_repository_package(stage, target_repository):
    destination = stage / "opt/distro/repository"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(target_repository, destination, symlinks=True)


def build_installer_repository(seed_repository, target_repository, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "packages").mkdir()

    seed_database = json.loads((seed_repository / "database.json").read_text())
    installer_seed_entry = next(
        package
        for package in seed_database["packages"]
        if package["identity"]["name"] == "installer-seed"
    )
    installer_seed = copy_package_entry(
        seed_repository, output, installer_seed_entry
    )

    with tempfile.TemporaryDirectory(prefix="distro-installer-packages-") as temporary:
        temporary = Path(temporary)

        control_stage = temporary / "control"
        control_stage.mkdir()
        stage_installer_control(control_stage)
        control = create_artifact(
            output, "installer-control", "1.0.0", control_stage
        )

        repository_stage = temporary / "repository"
        repository_stage.mkdir()
        stage_repository_package(repository_stage, target_repository)
        repository_package = create_artifact(
            output,
            "installer-target-repository",
            "1.0.0",
            repository_stage,
        )

        runtime = empty_package(output, "installer-runtime", "1.0.0")

    database = {
        "schema_version": 1,
        "prototype": True,
        "architecture": architecture(),
        "closed_build": True,
        "packages": [
            installer_seed,
            {
                **control,
                "depends": [],
                "conflicts": [],
                "provides": [],
            },
            {
                **repository_package,
                "depends": [],
                "conflicts": [],
                "provides": [],
            },
            {
                **runtime,
                "depends": [
                    {"name": "installer-seed"},
                    {"name": "installer-control"},
                    {"name": "installer-target-repository"},
                ],
                "conflicts": [],
                "provides": [{"name": "installer-runtime"}],
            },
        ],
    }
    # The copied Stage-0 installer seed carries its package relationships.
    if "depends" not in database["packages"][0]:
        database["packages"][0]["depends"] = []
    if "conflicts" not in database["packages"][0]:
        database["packages"][0]["conflicts"] = []
    if "provides" not in database["packages"][0]:
        database["packages"][0]["provides"] = [{"name": "installer-seed"}]

    write_json(output / "database.json", database)
    return database


def assemble_iso(iso_root, output):
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    required = (
        Path("/usr/bin/cpio"),
        Path("/usr/bin/gzip"),
        Path("/usr/bin/xorriso"),
        Path("/usr/lib/syslinux/bios/isolinux.bin"),
        Path("/usr/lib/syslinux/bios/ldlinux.c32"),
        Path("/boot/vmlinuz-linux"),
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"build-system root lacks ISO tools: {missing}")

    with tempfile.TemporaryDirectory(prefix="distro-iso-") as temporary:
        stage = Path(temporary) / "iso"
        (stage / "isolinux").mkdir(parents=True)
        (stage / "boot").mkdir(parents=True)

        shutil.copy2(
            "/usr/lib/syslinux/bios/isolinux.bin",
            stage / "isolinux/isolinux.bin",
        )
        shutil.copy2(
            "/usr/lib/syslinux/bios/ldlinux.c32",
            stage / "isolinux/ldlinux.c32",
        )
        shutil.copy2("/boot/vmlinuz-linux", stage / "boot/vmlinuz")

        (stage / "isolinux/isolinux.cfg").write_text(
            "DEFAULT distro\n"
            "PROMPT 0\n"
            "TIMEOUT 10\n"
            "\n"
            "LABEL distro\n"
            "  KERNEL /boot/vmlinuz\n"
            "  INITRD /boot/initramfs.img\n"
            "  APPEND console=tty0\n"
        )

        initramfs = stage / "boot/initramfs.img"
        command = (
            "set -euo pipefail; "
            f"cd {shlex_quote(str(iso_root))}; "
            "find . -xdev -print0 | sort -z | "
            f"cpio --null -o --format=newc --owner=0:0 | gzip -9 > {shlex_quote(str(initramfs))}"
        )
        subprocess.run(["/bin/bash", "-c", command], check=True)

        subprocess.run(
            [
                "/usr/bin/xorriso",
                "-as", "mkisofs",
                "-o", str(output),
                "-V", "DISTRO_INSTALL",
                "-J", "-R",
                "-b", "isolinux/isolinux.bin",
                "-c", "isolinux/boot.cat",
                "-no-emul-boot",
                "-boot-load-size", "4",
                "-boot-info-table",
                str(stage),
            ],
            check=True,
        )

    return {
        "schema_version": 1,
        "status": "success",
        "iso": str(output),
        "iso_sha256": sha256_file(output),
        "builder": "package-owned-xorriso",
        "initramfs": "managed installer-runtime root",
        "bootloader": "package:bootstrap-tools:syslinux",
        "kernel": "package:bootstrap-tools:/boot/vmlinuz-linux",
    }


def shlex_quote(value):
    import shlex
    return shlex.quote(value)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-repositories")
    build.add_argument("--seed-repository", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)

    iso = sub.add_parser("assemble-iso")
    iso.add_argument("--iso-root", type=Path, required=True)
    iso.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()

    if args.command == "build-repositories":
        root = args.output.resolve()
        root.mkdir(parents=True, exist_ok=True)
        for child in list(root.iterdir()):
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        target = root / "system-repository"
        installer = root / "installer-repository"
        build_target_repository(target)
        build_installer_repository(
            args.seed_repository.resolve(),
            target,
            installer,
        )
        result = {
            "schema_version": 1,
            "status": "success",
            "system_repository": str(target),
            "installer_repository": str(installer),
        }
    else:
        result = assemble_iso(args.iso_root.resolve(), args.output)

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
