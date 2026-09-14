#!/usr/bin/env python3
"""Build the prototype bootable installer ISO with Archiso."""

from __future__ import annotations
import argparse, json, shutil, subprocess, tempfile
from pathlib import Path

ARCHISO_PROFILE=Path("/usr/share/archiso/configs/releng")
LIVE_PACKAGES=("python","e2fsprogs","syslinux")

def repository_root():
    current=Path(__file__).resolve()
    for parent in current.parents:
        if (parent/"product/src/proto/manager/manage.py").is_file():
            return parent
    raise RuntimeError("unable to locate distro repository root")

def require_tool(name):
    path=shutil.which(name)
    if path is None:
        raise RuntimeError(f"{name} is required")
    return path

def append_packages(profile):
    package_file=profile/"packages.x86_64"
    existing={line.strip() for line in package_file.read_text().splitlines()
              if line.strip() and not line.lstrip().startswith("#")}
    additions=[name for name in LIVE_PACKAGES if name not in existing]
    if additions:
        with package_file.open("a") as output:
            output.write("\n# distro installer prototype\n")
            for name in additions:
                output.write(name+"\n")

def add_installer_files(profile, repository):
    root=repository_root()
    overlay=profile/"airootfs"
    distro_dir=overlay/"opt/distro"; distro_dir.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/"product/src/proto/manager/manage.py",distro_dir/"manage.py")
    shutil.copytree(repository,distro_dir/"repository",symlinks=True)
    bin_dir=overlay/"usr/local/bin"; bin_dir.mkdir(parents=True,exist_ok=True)
    installer=bin_dir/"install-distro"
    shutil.copy2(root/"product/src/proto/install/install_distro.py",installer)
    installer.chmod(0o755)
    motd=overlay/"etc/motd"; motd.parent.mkdir(parents=True,exist_ok=True)
    motd.write_text("\ndistro installer prototype\n--------------------------\n"
                    "Install to the QEMU virtio disk with:\n  install-distro /dev/vda\n\n")
    with (profile/"profiledef.sh").open("a") as output:
        output.write('\n# distro installer prototype\nfile_permissions["/usr/local/bin/install-distro"]="0:0:755"\n')

def build(repository, output):
    mkarchiso=require_tool("mkarchiso")
    if not ARCHISO_PROFILE.is_dir():
        raise RuntimeError(f"Archiso releng profile not found: {ARCHISO_PROFILE}; install the archiso package")
    repository=repository.resolve()
    if not (repository/"database.json").is_file():
        raise RuntimeError(f"invalid package repository: {repository}")
    output=output.resolve(); output.parent.mkdir(parents=True,exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="distro-archiso-") as td:
        work=Path(td); profile=work/"profile"
        shutil.copytree(ARCHISO_PROFILE,profile,symlinks=True)
        append_packages(profile); add_installer_files(profile,repository)
        archiso_work=work/"work"; archiso_out=work/"out"
        subprocess.run([mkarchiso,"-v","-r","-w",str(archiso_work),"-o",str(archiso_out),str(profile)],check=True)
        images=sorted(archiso_out.glob("*.iso"))
        if len(images)!=1:
            raise RuntimeError(f"expected one Archiso image, found {len(images)}")
        shutil.copy2(images[0],output)

    return {"schema_version":1,"status":"success","iso":str(output),"repository":str(repository),
            "builder":"archiso","installer_command":"install-distro /dev/vda"}

def main():
    p=argparse.ArgumentParser(description="Build the prototype distro installer ISO")
    p.add_argument("--repository",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("/tmp/distro-installer.iso"))
    a=p.parse_args()
    print(json.dumps(build(a.repository,a.output),indent=2,sort_keys=True))

if __name__=="__main__":
    main()
