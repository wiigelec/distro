"""Native FS-001 product requirement evaluation (not a regression suite)."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD_SRC = ROOT / "product" / "src"


def _run_selection():
    code = r'''from build.bootstrap.cross_toolchain import selected_steps
manifests, steps = selected_steps()
expected = (
    ("binutils-pass1", "binutils", "2.47"),
    ("gcc-pass1", "gcc", "16.2.0"),
    ("linux-headers", "linux", "7.1.8"),
    ("glibc", "glibc", "2.44"),
    ("gcc-libstdcpp", "gcc", "16.2.0"),
)
actual = tuple((s.id, s.name, s.version) for s in steps)
assert actual == expected, (actual, expected)
assert len({s.id for s in steps}) == len(steps)
assert all(s.name in manifests and s.recipe.is_file() and
           s.recipe.suffix == ".sh" and len(s.checksum) == 64 and
           s.checksum == s.checksum.lower() for s in steps)
assert set(steps[1].supplements) == {"gmp", "mpfr", "mpc"}
assert not steps[4].supplements
assert steps[1].recipe != steps[4].recipe
assert steps[1].checksum == steps[4].checksum
'''
    env = {"PATH": os.defpath, "PYTHONPATH": str(BUILD_SRC), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-B", "-c", code],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def selection_contract() -> bool:
    """Evaluate authoritative manifest/list/recipe resolution and exact ordering."""
    result = _run_selection()
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr)
        return False
    return True


def entrypoint_contract() -> bool:
    """Evaluate the documented CLI's command contract without constructing tools."""
    env = {"PATH": os.defpath, "PYTHONPATH": str(BUILD_SRC), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-B", "-m", "build.cli", "cross-toolchain", "--help"]
    result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode or "--root" not in result.stdout or "--check-host" not in result.stdout:
        print(result.stderr or result.stdout, file=sys.stderr)
        return False
    # The real build path must go through the shared Build construction entrypoint.
    cli = (BUILD_SRC / "build" / "cli.py").read_text(encoding="utf-8")
    return "run_stage(args.root)" in cli and "selected_steps()" in cli


def handoff_contract() -> bool:
    "Exercise archive and metadata acceptance/rejection without a toolchain rebuild."
    code = r'''import copy
import io
import json
from pathlib import Path
import tarfile
import tempfile
from build.bootstrap.cross_toolchain import _validate_candidate_archive
from build.bootstrap.cross_toolchain_metadata import (
    ARCHIVE_NAME, METADATA_NAME, sha256_file, validate_handoff,
    validate_published_handoff,
)

with tempfile.TemporaryDirectory(prefix="fs001-handoff-gate-") as tmp:
    folder = Path(tmp)
    archive = folder / ARCHIVE_NAME
    with tarfile.open(archive, "w:xz", format=tarfile.PAX_FORMAT) as t:
        directory = tarfile.TarInfo("./usr")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        t.addfile(directory)
        data = b"synthetic target payload"
        regular = tarfile.TarInfo("./usr/example")
        regular.size = len(data)
        regular.mode = 0o755
        t.addfile(regular, io.BytesIO(data))
        link = tarfile.TarInfo("./usr/example-link")
        link.type = tarfile.SYMTYPE
        link.linkname = "example"
        t.addfile(link)
    _validate_candidate_archive(archive)
    metadata = {
        "schema_version": 1,
        "artifact": {"type": "cross-toolchain", "stage": "1A",
                     "filename": ARCHIVE_NAME, "format": "tar.xz",
                     "sha256": sha256_file(archive), "size_bytes": archive.stat().st_size},
        "toolchain": {"target": "x86_64-distro-linux-gnu",
                      "sysroot": "/toolchain", "tools_prefix": "/toolchain/tools"},
        "sources": [{"step": "synthetic"}],
        "verification": {"functional": "passed", "relocation": "passed"},
    }
    validate_handoff(archive, metadata)
    (folder / METADATA_NAME).write_text(json.dumps(metadata), encoding="utf-8")
    assert validate_published_handoff(folder) == metadata
    def rejected(m):
        try:
            validate_handoff(archive, m)
        except ValueError:
            return True
        return False
    broken = copy.deepcopy(metadata)
    broken["artifact"]["sha256"] = "0" * 64
    assert rejected(broken), "corrupted digest accepted"
    broken = copy.deepcopy(metadata)
    broken["artifact"]["size_bytes"] += 1
    assert rejected(broken), "wrong size accepted"
    broken = copy.deepcopy(metadata)
    broken["verification"]["relocation"] = "failed"
    assert rejected(broken), "incomplete verification accepted"
    (folder / METADATA_NAME).unlink()
    try:
        validate_published_handoff(folder)
    except ValueError:
        pass
    else:
        raise AssertionError("missing metadata completion marker accepted")
    with tarfile.open(archive, "w:xz", format=tarfile.PAX_FORMAT) as t:
        a = tarfile.TarInfo("./unsafe")
        a.type = tarfile.SYMTYPE
        a.linkname = "/etc"
        t.addfile(a)
        b = tarfile.TarInfo("./unsafe/escape")
        b.size = 1
        t.addfile(b, io.BytesIO(b"x"))
    try:
        _validate_candidate_archive(archive)
    except RuntimeError:
        pass
    else:
        raise AssertionError("archive containing child beneath symlink accepted")
'''
    env = {"PATH": os.defpath, "PYTHONPATH": str(BUILD_SRC), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                            env=env, capture_output=True, text=True)
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr)
        return False
    return True



def _contract_subprocess(code: str) -> bool:
    env = {"PATH": os.defpath, "PYTHONPATH": str(BUILD_SRC), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                            env=env, capture_output=True, text=True)
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr)
        return False
    return True


def workspace_recipe_sandbox_contract() -> bool:
    """Exercise per-step roots, sandbox invocation, environment, and mount rejection."""
    code = r'''from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import subprocess
from build.bootstrap import cross_toolchain as ct
from build import host_sandbox as hs
from build.selection import Step, Source, Manifest

with TemporaryDirectory(prefix="fs001-native-contract-") as directory:
    root = Path(directory)
    work = root / "build"
    work.mkdir()
    installed = root / "root"
    installed.mkdir()
    cache = work / "sources"
    cache.mkdir()
    recipe = root / "step.sh"
    recipe.write_text("#!/bin/bash\nexit 0\n")
    manifest = Manifest("gcc", Source("https://example.invalid/{version}","sha256"), (), (), {})
    step1 = Step("gcc-pass1", "gcc", "16.2.0", recipe, "a"*64, {})
    step2 = Step("gcc-libstdcpp", "gcc", "16.2.0", recipe, "a"*64, {})
    extracted = []
    def extract(_archive, dest):
        dest.mkdir()
        extracted.append(dest)
    with patch.object(ct,"_archive",return_value=root/"download.tar.xz"), patch.object(ct,"_extract_single",side_effect=extract):
        first = ct.prepare_step(step1,manifest,work,cache)
        second = ct.prepare_step(step2,manifest,work,cache)
    assert first[0] != second[0] and first[1] != second[1]
    assert first[0].parent == work/"steps"/"gcc-pass1"
    assert second[0].parent == work/"steps"/"gcc-libstdcpp"
    assert all(p.is_dir() for p in (*first,*second))
    try:
        ct.prepare_step(step1,manifest,work,cache)
    except Exception:
        pass
    else:
        raise AssertionError("reused step workspace accepted")
    with patch.object(hs,"_bwrap",return_value="/usr/bin/bwrap"):
        cmd = hs.recipe_command(work,installed,recipe,source_dir="/work/steps/gcc-pass1/source",
               build_dir="/work/steps/gcc-pass1/build",package="gcc",version="16.2.0",
               step_id="gcc-pass1",target="x86_64-distro-linux-gnu",jobs=2)
        for flag in ("--unshare-user","--unshare-pid","--unshare-net","--clearenv","--ro-bind","--bind","--setenv"):
            assert flag in cmd, flag
        assert cmd.count("--bind") == 2
        assert cmd[cmd.index("--bind")+2] == "/work"
        assert cmd[cmd.index("--bind",cmd.index("--bind")+1)+2] == "/toolchain"
        assert cmd[-2:] == ["/bin/bash","/recipe/selected.sh"]
        for label,value in (("DISTRO_ROOT_DIR","/toolchain"),("DISTRO_PACKAGE_VERSION","16.2.0"),
                            ("DISTRO_TARGET","x86_64-distro-linux-gnu"),("HOME","/work")):
            assert ["--setenv",label,value] == cmd[cmd.index(label)-1:cmd.index(label)+2]
        assert "LD_LIBRARY_PATH" not in cmd and "CPATH" not in cmd
        assert "--" in cmd
        try:
            hs.recipe_command(work,installed,recipe,source_dir="/etc",build_dir="/work/steps/gcc-pass1/build",
                   package="gcc",version="16.2.0",step_id="gcc-pass1")
        except hs.SandboxError:
            pass
        else:
            raise AssertionError("outside source directory accepted")
        try:
            hs._workspace_mounts(work,work)
        except hs.SandboxError:
            pass
        else:
            raise AssertionError("overlapping writable mounts accepted")
    # A missing sandbox executable cannot fall through to unrestricted execution.
    with patch.object(hs.shutil,"which",return_value=None):
        try:
            hs._base_command()
        except hs.SandboxError:
            pass
        else:
            raise AssertionError("missing bwrap accepted")
    # Recipe invocation must use the constructed sandbox command, never bare bash.
    with patch.object(hs,"recipe_command",return_value=["false"]), patch.object(hs.subprocess,"run",side_effect=subprocess.CalledProcessError(1,"false")) as runner:
        try:
            hs.run_recipe()
        except hs.SandboxError:
            pass
        else:
            raise AssertionError("failed sandbox command accepted")
        runner.assert_called_once()
'''
    return _contract_subprocess(code)


def verified_source_contract() -> bool:
    """Exercise HTTPS source checksum rejection, successful publication, and cleanup."""
    code = r'''from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import io
import hashlib
from build.selection import Source, SelectionError
from build.sources import fetch_verified

class Response(io.BytesIO):
    def __init__(self, content, url):
        super().__init__(content)
        self.url=url
    def geturl(self): return self.url
    def __enter__(self): return self
    def __exit__(self,*args): self.close()

with TemporaryDirectory(prefix="fs001-source-contract-") as tmp:
    dest = Path(tmp)/"verified.tar.xz"
    payload = b"verified upstream archive bytes"
    digest = hashlib.sha256(payload).hexdigest()
    source = Source("https://example.invalid/archive-{version}.tar.xz","sha256")
    with patch("build.sources.urlopen",side_effect=lambda url,timeout: Response(payload,url)) as opener:
        assert fetch_verified(source,"1.2",dest,digest) == dest
        assert dest.read_bytes() == payload
        assert opener.call_args.args[0].endswith("archive-1.2.tar.xz")
    dest.unlink()
    with patch("build.sources.urlopen",side_effect=lambda url,timeout: Response(payload,url)):
        try:
            fetch_verified(source,"1.2",dest,"0"*64)
        except SelectionError:
            pass
        else:
            raise AssertionError("wrong checksum accepted")
    assert not dest.exists() and not dest.with_name(dest.name+".partial").exists()
    with patch("build.sources.urlopen",side_effect=lambda url,timeout: Response(payload,"http://example.invalid/archive")):
        try:
            fetch_verified(source,"1.2",dest,digest)
        except SelectionError:
            pass
        else:
            raise AssertionError("insecure redirect accepted")
    assert not dest.exists() and not dest.with_name(dest.name+".partial").exists()
    try:
        fetch_verified(Source("http://example.invalid/{version}","sha256"),"1.2",dest,digest)
    except SelectionError:
        pass
    else:
        raise AssertionError("insecure URL accepted")
'''
    return _contract_subprocess(code)



def failure_integrity_contract() -> bool:
    """Exercise failure propagation and incomplete handoff cleanup without rebuilding."""
    code = r'''from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
import io,tarfile,subprocess
from build.bootstrap import cross_toolchain as ct
from build.bootstrap import cross_toolchain_metadata as md
from build.selection import SelectionError

def rejected(fn, exception):
    try: fn()
    except exception: return
    raise AssertionError("expected failure was accepted")

with TemporaryDirectory(prefix="fs001-failure-gate-") as tmp:
    root=Path(tmp)
    installed=root/"root"
    installed.mkdir()
    (installed/"sentinel").write_text("installed")
    build=root/"build"
    build.mkdir()
    artifacts=root/"artifacts"
    artifacts.mkdir()
    # Invalid partial handoffs cannot be considered completed artifacts.
    (artifacts/md.ARCHIVE_NAME).write_bytes(b"partial")
    rejected(lambda: md.validate_published_handoff(artifacts), ValueError)
    (artifacts/md.ARCHIVE_NAME).unlink()
    # Construction failures propagate and cannot publish handoff metadata.
    construction=root/"construction"
    construction.mkdir()
    with patch.object(ct,"selected_steps",return_value=({},[SimpleNamespace(id="bad",name="bad",version="1",recipe=root/"missing.sh")])), \
         patch.object(ct,"qualify_host"), patch.object(ct,"probe_bubblewrap"), \
         patch.object(ct,"_host_jobs",return_value=1), \
         patch.object(ct,"prepare_step",side_effect=SelectionError("source rejected")):
        rejected(lambda: ct.run_stage(construction), RuntimeError)
    assert not (artifacts/md.METADATA_NAME).exists()
    # Pre-existing handoffs must not be silently replaced.
    (artifacts/md.ARCHIVE_NAME).write_bytes(b"existing")
    rejected(lambda: ct.publish_archive(root,installed,target=ct.TARGET,steps=[],host_triplet="host",started=0),RuntimeError)
    assert (artifacts/md.ARCHIVE_NAME).read_bytes()==b"existing"
    (artifacts/md.ARCHIVE_NAME).unlink()
    # Inject failure after archive rename and before metadata publication.
    # This tests the cleanup block at the actual two-file commit boundary.
    real_replace=Path.replace
    def fail_metadata_replace(self,target):
        if self.name == md.METADATA_NAME:
            raise OSError("simulated metadata publication failure")
        return real_replace(self,target)
    def make_archive(args,**kwargs):
        if args[0]=="tar" and "-cJf" in args:
            candidate=Path(args[args.index("-cJf")+1])
            with tarfile.open(candidate,"w:xz",format=tarfile.PAX_FORMAT) as t:
                info=tarfile.TarInfo("./sentinel")
                data=b"installed"
                info.size=len(data)
                t.addfile(info,io.BytesIO(data))
        elif args[0]=="tar" and "-xJf" in args:
            pass
        else: raise AssertionError("unexpected subprocess")
        return subprocess.CompletedProcess(args,0)
    with patch.object(ct.subprocess,"run",side_effect=make_archive), \
         patch.object(ct,"verify_cross_toolchain"), \
         patch.object(ct,"make_metadata",return_value={"synthetic":True}), \
         patch.object(ct,"validate_handoff"), \
         patch.object(Path,"replace",new=fail_metadata_replace):
        rejected(lambda: ct.publish_archive(root,installed,target=ct.TARGET,steps=[],host_triplet="host",started=0),OSError)
    assert not (artifacts/md.ARCHIVE_NAME).exists(), "archive survived failed metadata publication"
    assert not (artifacts/md.METADATA_NAME).exists(), "metadata survived failed metadata publication"
    # Relocation verification failure occurs before either publication.
    with patch.object(ct.subprocess,"run",side_effect=make_archive), \
         patch.object(ct,"verify_cross_toolchain",side_effect=RuntimeError("relocation failed")):
        rejected(lambda: ct.publish_archive(root,installed,target=ct.TARGET,steps=[],host_triplet="host",started=0),RuntimeError)
    assert not (artifacts/md.ARCHIVE_NAME).exists()
    assert not (artifacts/md.METADATA_NAME).exists()
'''
    return _contract_subprocess(code)


def functional_relocation_evidence_contract() -> bool:
    """Check immutable FS-001 handoff evidence identity; do not claim to rerun compilation."""
    import json
    from pathlib import Path
    evidence_path = ROOT / "product" / "validation" / "fs001-stage1a-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    expected = {
        "source_revision": "f9d34c58308e7d9f66033ec9256b51b79feefc3c",
        "target": "x86_64-distro-linux-gnu",
        "archive_sha256": "05eccf763bb6621553a0a738cba9e88c7b0e562194eeb535f4b9587b39ddc9b7",
        "archive_size_bytes": 469689576,
        "archive_entries": 4625,
        "functional": "passed",
        "relocation": "passed",
    }
    for key, value in expected.items():
        if evidence.get(key) != value:
            print(f"FAIL FS-001 evidence {key}: {evidence.get(key)!r}", file=sys.stderr)
            return False
    if evidence.get("evidence_kind") != "recorded-completed-build-and-independent-handoff-inspection":
        return False
    return True
