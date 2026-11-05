"""Bounded FS-002 diagnostic: collision-safe staged installs through native GCC.

Native GCC is installed only to separate staging; ownership transitions,
functional verification, and artifact publication remain gated.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import stat
import time

from build.bootstrap.cross_toolchain import TARGET, _host_jobs, prepare_step
from build.bootstrap.cross_chroot_ownership import (
    check_staged_install, merge_staged_install, require_preserved_imports,
    snapshot_imported_root,
)
from build.bootstrap.cross_chroot_sandbox import run_staged_recipe
from build.bootstrap.cross_chroot_transitions import native_collision_evidence
from build.selection import SelectionError


def omit_generated_info_index(stage: Path) -> None:
    """Exclude only GNU Info's shared, generated menu index from staged DESTDIR.

    Individual .info manuals remain staged. Rebuilding the combined target
    index is a later governed operation, not an ownership collision exception.
    """
    index = stage / "usr/share/info/dir"
    try:
        mode = index.lstat().st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISREG(mode):
        raise SelectionError(f"unexpected staged GNU Info index type: {index}")
    index.unlink()


def omit_native_gcc_staging_lib64_link(stage: Path) -> None:
    """Verify GCC installed through the merged-/usr alias, then drop its duplicate.

    Stage /usr/lib64 is not part of the payload to merge: the imported root
    already owns that exact link. Never delete a real directory or other link.
    Installed runtime files remain in the real stage /usr/lib directory.
    """
    canonical = stage / "usr/lib"
    alias = stage / "usr/lib64"
    try:
        canonical_mode = canonical.lstat().st_mode
        alias_mode = alias.lstat().st_mode
    except FileNotFoundError as exc:
        raise SelectionError("native GCC staging merged-/usr layout is incomplete") from exc
    if not stat.S_ISDIR(canonical_mode) or stat.S_ISLNK(canonical_mode):
        raise SelectionError("native GCC staging usr/lib must be a real directory")
    if not stat.S_ISLNK(alias_mode) or os.readlink(alias) != "lib":
        raise SelectionError("native GCC staging usr/lib64 must be a link to lib")
    alias.unlink()


REVIEWED_GCC_DUPLICATES = {'usr/lib/libstdc++.so': ['link', 511, 'libstdc++.so.6.0.36'], 'usr/lib/libstdc++.so.6': ['link', 511, 'libstdc++.so.6.0.36'], 'usr/lib/libstdc++.so.6.0.36-gdb.py': ['file', 420, 'e902dff806755b242bdb7d60f7ee147f8b96dac10668c9bba5774445cb301f9d'], 'usr/lib/libstdc++exp.la': ['file', 493, 'a981392b76b0b6b0f117aa50806cdb52e2de711230e963b62333eb3d3e387261'], 'usr/lib/libstdc++fs.la': ['file', 493, 'a409dc0be5efb4829d00f18063db4f03db0a326cadf136ec13b7fc72019c5d1c'], 'usr/lib/libsupc++.la': ['file', 493, 'b5a25b60e4df965e89506ed5a1818025f5d8130319937e429c0e96b3444d6929'], 'usr/share/gcc-16.2.0/python/libstdcxx/__init__.py': ['file', 420, '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'], 'usr/share/gcc-16.2.0/python/libstdcxx/v6/__init__.py': ['file', 420, 'b431bb0caac43dc1e20bf29c21026539dbfd40dd22f85539d59327d9d172cee5'], 'usr/share/gcc-16.2.0/python/libstdcxx/v6/printers.py': ['file', 420, '72bb3b2fcfef5ef438fba84376e93d5aff85fcde4aaf45d38db0790c99b3011c'], 'usr/share/gcc-16.2.0/python/libstdcxx/v6/xmethods.py': ['file', 420, '2d4ce7ea282617969f435ff59a14430f77907720ba28171808f7b9809df77993']}
REVIEWED_GCC_DIFFERING = frozenset(['usr/lib/libstdc++.a', 'usr/lib/libstdc++.la', 'usr/lib/libstdc++.modules.json', 'usr/lib/libstdc++.so.6.0.36', 'usr/lib/libstdc++exp.a', 'usr/lib/libstdc++fs.a', 'usr/lib/libsupc++.a'])


def preserve_reviewed_native_gcc_duplicates(stage: Path, collisions: dict, imported_baseline: dict) -> dict:
    """Omit exactly ten byte-identical FS-001 entries, retaining audit evidence.

    This grants no replacement rights to the differing native runtime objects.
    Only exact-path, exact-mode, exact-content imported duplicates qualify.
    """
    reviewed = {name: tuple(identity) for name, identity in REVIEWED_GCC_DUPLICATES.items()}
    for name, identity in reviewed.items():
        pair = collisions.get(name)
        if pair is None or pair != (identity, identity):
            raise SelectionError(f"reviewed GCC duplicate absent or changed: {name}")
        if imported_baseline.get(name) != identity:
            raise SelectionError(f"GCC duplicate is not owned by verified FS-001 import: {name}")
    # The seven differing paths are inventory-only; never delete or replace them.
    if set(collisions) != set(reviewed) | REVIEWED_GCC_DIFFERING:
        raise SelectionError("native GCC collision set diverged from reviewed inventory")
    for name in sorted(reviewed):
        (stage / name).unlink()
    return {name: list(identity) for name, identity in sorted(reviewed.items())}


# Exact imported FS-001 identities for the seven native GCC runtime overlaps.
# Candidate identities are recorded per verified build; GCC static archives can vary.
REVIEWED_GCC_PRIOR_RUNTIME = {'usr/lib/libstdc++.a': (420, '617d14fe2286b14b53c95f244f5b42c9db4e74ab3e9fd038ab706e27645137d7'), 'usr/lib/libstdc++.la': (493, '86da35442e9e176eef0c2adbf128c30ff8516b0e6ce9f2ec10fffcf86cd7b615'), 'usr/lib/libstdc++.modules.json': (420, 'd670cc25b4640f2facad8f6483e91884b63c6d53cfbd697989e07c8b7cbf372a'), 'usr/lib/libstdc++.so.6.0.36': (493, 'ec29336384e69667b163e0be937127d3b91fa4712d36dc66834521b00ea7102d'), 'usr/lib/libstdc++exp.a': (420, '376be2a7035b0f9872a92105f371fd9555f4edbd4d95f950c972fba6f634c0a1'), 'usr/lib/libstdc++fs.a': (420, 'cd481263d737a1d29e1baabf223c9b89a5da6d129425a111d934718abf525fbb'), 'usr/lib/libsupc++.a': (420, '12cd9bb171538a34b6df4f28cb8f3e53957ed2ab5334815df995999422e14496')}


def construct_native_gcc_candidate_root(
    installed: Path, stage: Path, staging_root: Path,
    imported_baseline: dict, collisions: dict,
) -> dict:
    """Create a separately copied native-GCC candidate; never mutate FS-001.

    Both the seven approved overlaps and all additions are installed through
    the existing no-overwrite staging preflight, into a private full copy.
    The caller still stops before native execution, root promotion or publish.
    """
    expected_names = set(REVIEWED_GCC_PRIOR_RUNTIME)
    if set(collisions) != expected_names:
        raise SelectionError("native GCC runtime transition paths changed")
    # Preserve the full imported baseline: a matching installed file alone
    # does not establish that it was present in the FS-001 archive.
    original_snapshot = snapshot_imported_root(installed)
    staged_snapshot = snapshot_imported_root(stage)
    provenance = {}
    invalid = []
    for name, (mode, digest) in sorted(REVIEWED_GCC_PRIOR_RUNTIME.items()):
        prior, incoming = collisions[name]
        expected_prior = ("file", mode, digest)
        imported = imported_baseline.get(name)
        installed_identity = original_snapshot.get(name)
        installed_ok = prior == expected_prior and installed_identity == prior
        imported_ok = imported == expected_prior
        staged_ok = (
            incoming[0] == "file" and incoming[1] == mode and
            isinstance(incoming[2], str) and len(incoming[2]) == 64 and
            all(c in "0123456789abcdef" for c in incoming[2])
        )
        provenance[name] = {
            "expected_prior": list(expected_prior),
            "imported_baseline": list(imported) if imported is not None else None,
            "installed": list(installed_identity) if installed_identity is not None else None,
            "staged": list(incoming),
            "installed_matches_reviewed": installed_ok,
            "imported_matches_reviewed": imported_ok,
            "staged_identity_valid": staged_ok,
            "imported_baseline_missing": imported is None,
        }
        if not (installed_ok and imported_ok and staged_ok):
            invalid.append(name)
    provenance_report = staging_root / "native-gcc-ownership-provenance.json"
    with provenance_report.open("x", encoding="utf-8") as output:
        json.dump({
            "schema_version": 1,
            "step_id": "native-gcc",
            "state": "diagnostic-no-ownership-authorization",
            "invalid_paths": invalid,
            "paths": provenance,
        }, output, indent=2, sort_keys=True)
        output.write("\n")
    if invalid:
        raise SelectionError(
            f"GCC ownership provenance failed for {len(invalid)} paths; "
            f"inspect {provenance_report}; original root preserved"
        )
    reviewed = {
        name: {"installed": list(pair[0]), "staged": list(pair[1])}
        for name, pair in sorted(collisions.items())
    }
    if any(original_snapshot.get(name) != tuple(identity)
           for name, identity in imported_baseline.items()):
        raise SelectionError("FS-001 imported ownership changed before trial")
    candidate = staging_root / "native-gcc-candidate-root"
    if candidate.exists() or candidate.is_symlink():
        raise SelectionError("GCC candidate root already exists")
    # Full copy, NOT hard links: later native verification must not be able to
    # mutate the imported root via shared inodes. Preserve symlinks as symlinks.
    shutil.copytree(installed, candidate, symlinks=True)
    if snapshot_imported_root(candidate) != original_snapshot:
        raise SelectionError("GCC candidate copy differs from imported root")
    # Remove only the seven verified old *copies* in the candidate, then use
    # the standard collision-rejecting merge for the staged GCC payload.
    for name in sorted(expected_names):
        (candidate / name).unlink()
    merge_staged_install(candidate, stage)
    if snapshot_imported_root(stage) != staged_snapshot:
        raise SelectionError("native GCC staging changed during candidate construction")
    after = snapshot_imported_root(candidate)
    expected = original_snapshot.copy()
    expected.update(staged_snapshot)
    if after != expected:
        raise SelectionError("candidate root differs from approved GCC staging result")
    if snapshot_imported_root(installed) != original_snapshot:
        raise SelectionError("imported root changed during GCC candidate construction")
    return {
        "schema_version": 1, "step_id": "native-gcc",
        "state": "diagnostic-candidate-not-promoted",
        "candidate_root": str(candidate),
        "reviewed_runtime_transitions": reviewed,
        "imported_entry_count": len(original_snapshot),
        "candidate_entry_count": len(after),
    }



def verify_native_gcc_candidate(
    installed: Path, candidate: Path, staging_root: Path,
    imported_baseline: dict,
) -> dict:
    """Smoke-test target-native utilities and C/C++ inside the candidate root.

    Bubblewrap exposes NO host /usr, /bin, /lib, /lib64 or /etc. A read-only
    candidate is the sandbox /, with only an isolated scratch directory writable.
    This diagnostic grants neither ownership promotion nor publication rights.
    """
    import subprocess

    from build.host_sandbox import _bwrap, _workspace_mounts

    candidate = Path(candidate).absolute()
    installed = Path(installed).absolute()
    staging_root = Path(staging_root).absolute()
    if candidate != staging_root / "native-gcc-candidate-root":
        raise SelectionError("native verification candidate must be the reviewed GCC root")
    if not candidate.is_dir() or candidate.is_symlink():
        raise SelectionError("native GCC candidate must be a real directory")
    if not installed.is_dir() or installed.is_symlink():
        raise SelectionError("installed root must be a real directory")
    before_candidate = snapshot_imported_root(candidate)
    before_installed = snapshot_imported_root(installed)
    require_preserved_imports(installed, imported_baseline)
    scratch = staging_root / "native-gcc-verification-scratch"
    if scratch.exists() or scratch.is_symlink():
        raise SelectionError("native GCC verification scratch already exists")
    scratch.mkdir(mode=0o700)
    # Apply the established no-symlink / no-overlap writable-root guard.
    _workspace_mounts(scratch, candidate)
    (scratch / "smoke.c").write_text(
        "#include <stdio.h>\nint main(void){puts(\"NATIVE_C_OK\");return 0;}\n",
        encoding="utf-8",
    )
    (scratch / "smoke.cpp").write_text(
        '#include <iostream>\n#include <string>\n'
        'int main(){std::string s="NATIVE_CPP_OK";std::cout<<s<<"\\n";return 0;}\n',
        encoding="utf-8",
    )
    checks = r"""
set -euo pipefail
export PATH=/usr/bin:/bin LC_ALL=C HOME=/verify TMPDIR=/verify
for tool in bash sh cat grep sed gawk make diff tar as ld ar readelf gcc g++; do
    command -v "$tool" >/dev/null || { printf 'MISSING:%s\n' "$tool"; exit 20; }
done
printf 'alpha\n' | /usr/bin/sed 's/alpha/beta/' | /usr/bin/grep -qx beta
printf '1 2\n' | /usr/bin/gawk '{exit ($1+$2 == 3 ? 0 : 1)}'
printf 'hello\n' > /verify/a.txt
/usr/bin/cat /verify/a.txt > /verify/b.txt
/usr/bin/diff -q /verify/a.txt /verify/b.txt >/dev/null
/usr/bin/tar -cf /verify/test.tar -C /verify a.txt
/usr/bin/gcc -O0 -o /verify/smoke-c /verify/smoke.c
/usr/bin/g++ -O0 -o /verify/smoke-cpp /verify/smoke.cpp
[[ "$(/verify/smoke-c)" == NATIVE_C_OK ]]
[[ "$(/verify/smoke-cpp)" == NATIVE_CPP_OK ]]
/usr/bin/readelf -h /verify/smoke-c | /usr/bin/grep -q 'ELF64'
/usr/bin/readelf -l /verify/smoke-c | /usr/bin/grep -q 'Requesting program interpreter'
/usr/bin/readelf -l /verify/smoke-cpp | /usr/bin/grep -q 'Requesting program interpreter'
printf 'NATIVE_BASH_UTILITIES_C_CPP_OK\n'
"""
    # Bubblewrap requires mount targets to exist before it can mount /dev,
    # /proc, /tmp, /run and /verify. The candidate itself must remain immutable:
    # construct a private verification copy and add only missing mountpoints.
    verification_root = staging_root / "native-gcc-verification-root"
    if verification_root.exists() or verification_root.is_symlink():
        raise SelectionError("native GCC verification root already exists")
    shutil.copytree(candidate, verification_root, symlinks=True)
    verification_snapshot = snapshot_imported_root(verification_root)
    if verification_snapshot != before_candidate:
        raise SelectionError("native GCC verification copy differs from candidate")
    for name in ("dev", "proc", "tmp", "run", "verify"):
        mountpoint = verification_root / name
        if mountpoint.is_symlink():
            raise SelectionError(f"verification mountpoint is a symlink: {name}")
        if mountpoint.exists():
            if not mountpoint.is_dir():
                raise SelectionError(f"verification mountpoint is not a directory: {name}")
        else:
            mountpoint.mkdir(mode=0o755)
    # No host userspace mounts: only the target-derived verification copy is /
    # and a separate scratch mount is writable. The candidate stays unchanged.
    cmd = [
        _bwrap(), "--die-with-parent", "--unshare-user", "--unshare-pid",
        "--unshare-net", "--new-session", "--clearenv",
        "--ro-bind", str(verification_root), "/", "--dev", "/dev",
        "--proc", "/proc", "--tmpfs", "/tmp", "--tmpfs", "/run",
        "--bind", str(scratch), "/verify",
        "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LC_ALL", "C",
        "--setenv", "HOME", "/verify", "--setenv", "TMPDIR", "/verify",
        "--chdir", "/verify", "--", "/bin/bash", "-c", checks,
    ]
    report = staging_root / "native-gcc-functional-verification.json"
    try:
        result = subprocess.run(
            cmd, env={"PATH": os.defpath}, text=True, capture_output=True,
            timeout=180,
        )
        success = result.returncode == 0 and "NATIVE_BASH_UTILITIES_C_CPP_OK" in result.stdout
        payload = {
            "schema_version": 1, "step_id": "native-gcc",
            "state": "diagnostic-functional-smoke-not-accepted",
            "isolated_candidate_root": str(candidate),
            "host_userspace_mounted": False,
            "exit_code": result.returncode,
            "success": success,
            "stdout": result.stdout[-16000:], "stderr": result.stderr[-16000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        success = False
        payload = {
            "schema_version": 1, "step_id": "native-gcc",
            "state": "diagnostic-functional-smoke-not-accepted",
            "isolated_candidate_root": str(candidate),
            "host_userspace_mounted": False, "success": False,
            "error": str(exc),
        }
    # Record the representative ELF interpreter and dependency closure using
    # candidate paths only. The same check runs after independent restoration.
    if success:
        from build.bootstrap.cross_chroot_elf_audit import audit_native_elf
        audit_report = staging_root / "native-gcc-elf-dependencies.json"
        audit = audit_native_elf(candidate, scratch, audit_report)
        payload["elf_dependencies"] = {
            "success": audit["success"],
            "dependency_graph_sha256": audit["dependency_graph_sha256"],
            "elf_object_count": audit["elf_object_count"],
            "errors": audit["errors"],
        }
        if not audit["success"]:
            success = False
            payload["success"] = False
            payload["state"] = "diagnostic-elf-dependency-audit-failed"
    # Sandbox is read-only for the candidate, and the root saved before GCC
    # candidate creation must still match exactly on all imported entries.
    if snapshot_imported_root(candidate) != before_candidate:
        raise SelectionError("native functional check modified candidate filesystem")
    if snapshot_imported_root(installed) != before_installed:
        raise SelectionError("native functional check modified original installed root")
    require_preserved_imports(installed, imported_baseline)
    with report.open("x", encoding="utf-8") as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")
    if not success:
        raise SelectionError(f"native GCC candidate functional smoke failed; inspect {report}")
    return payload



def verify_native_gcc_relocation(
    installed: Path, candidate: Path, staging_root: Path,
    imported_baseline: dict,
) -> dict:
    """Diagnostic-only candidate archive -> independent restore -> native smoke.

    This MUST NOT publish an artifact or a completion marker. The restored root
    resides outside the construction workspace, and its sandbox receives no
    mounts from that workspace or the host's userspace.
    """
    import hashlib
    import subprocess
    import tempfile
    from build.bootstrap.cross_toolchain import _validate_candidate_archive

    installed, candidate, staging_root = map(
        lambda p: Path(p).absolute(), (installed, candidate, staging_root)
    )
    if candidate != staging_root / "native-gcc-candidate-root":
        raise SelectionError("relocation requires the reviewed native GCC candidate")
    if not candidate.is_dir() or candidate.is_symlink():
        raise SelectionError("missing native GCC relocation candidate")
    if (staging_root / "native-gcc-functional-verification.json").is_file() is False:
        raise SelectionError("native functional verification evidence is missing")
    smoke = json.loads((staging_root / "native-gcc-functional-verification.json").read_text())
    if smoke.get("success") is not True:
        raise SelectionError("native functional smoke has not passed")
    before_candidate = snapshot_imported_root(candidate)
    before_installed = snapshot_imported_root(installed)
    require_preserved_imports(installed, imported_baseline)
    archive = staging_root / "native-gcc-relocation-candidate.tar.xz"
    report = staging_root / "native-gcc-relocation-verification.json"
    if archive.exists() or archive.is_symlink() or report.exists() or report.is_symlink():
        raise SelectionError("relocation archive or evidence already exists")
    payload = {
        "schema_version": 1, "step_id": "native-gcc",
        "state": "diagnostic-relocation-not-published",
        "success": False, "archive": str(archive),
        "independent_restoration": True,
        "host_userspace_mounted": False,
    }
    try:
        # GNU tar emits a filesystem-only archive. Fail before restoration if
        # member names, symlink traversal, or hardlink targets are unsafe.
        subprocess.run(
            ["tar", "--format=posix", "-cJf", str(archive), "-C", str(candidate), "."],
            check=True, env={"PATH": os.defpath}, timeout=600,
        )
        _validate_candidate_archive(archive)
        digest = hashlib.sha256()
        with archive.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        payload.update({"archive_size": archive.stat().st_size,
                        "archive_sha256": digest.hexdigest()})
        # tmpdir is outside staging; neither construction nor original root is
        # available inside the sandbox used by verify_native_gcc_candidate().
        with tempfile.TemporaryDirectory(prefix="distro-fs002-relocation-") as tmp:
            restore_staging = Path(tmp) / "staging"
            restore_staging.mkdir()
            restored = restore_staging / "native-gcc-candidate-root"
            restored.mkdir()
            subprocess.run(
                ["tar", "-xJf", str(archive), "-C", str(restored),
                 "--no-same-owner", "--no-overwrite-dir"],
                check=True, env={"PATH": os.defpath}, timeout=600,
            )
            if snapshot_imported_root(restored) != before_candidate:
                raise SelectionError("restored candidate identity differs from archived candidate")
            relocated_smoke = verify_native_gcc_candidate(
                installed, restored, restore_staging, imported_baseline
            )
            if relocated_smoke.get("success") is not True:
                raise SelectionError("restored candidate functional verification failed")
            if (smoke.get("elf_dependencies", {}).get("dependency_graph_sha256") !=
                    relocated_smoke.get("elf_dependencies", {}).get("dependency_graph_sha256")):
                raise SelectionError("ELF dependency graph changed after independent restoration")
            payload["relocated_smoke"] = {
                "success": True,
                "exit_code": relocated_smoke.get("exit_code"),
                "stdout": relocated_smoke.get("stdout", "")[-4000:],
                "elf_dependencies": relocated_smoke.get("elf_dependencies"),
            }
        if snapshot_imported_root(candidate) != before_candidate:
            raise SelectionError("relocation changed the native GCC candidate")
        if snapshot_imported_root(installed) != before_installed:
            raise SelectionError("relocation changed the original installed root")
        require_preserved_imports(installed, imported_baseline)
        payload["success"] = True
    except Exception as exc:
        payload["error"] = str(exc)
        raise
    finally:
        # This is diagnostic evidence, NOT Stage 1C handoff metadata.
        with report.open("x", encoding="utf-8") as output:
            json.dump(payload, output, sort_keys=True, indent=2)
            output.write("\n")
    return payload


def verify_native_binutils_structure(root: Path) -> None:
    """Check native Binutils executables without running target binaries.

    ELF structure is only an initial sanity gate, not functional verification.
    """
    for name in ("as", "ld", "ar", "nm", "objdump", "readelf"):
        path = root / "usr/bin" / name
        try:
            meta = path.lstat()
        except FileNotFoundError as exc:
            raise SelectionError(f"missing native Binutils executable: {path}") from exc
        if not stat.S_ISREG(meta.st_mode) or not meta.st_mode & 0o111:
            raise SelectionError(f"native Binutils executable must be a regular executable file: {path}")
        with path.open("rb") as executable:
            header = executable.read(64)
        # ELF64, little-endian, x86-64; executable or position-independent executable.
        if (len(header) < 64 or header[:4] != b"\x7fELF" or
                header[4] != 2 or header[5] != 1 or
                int.from_bytes(header[16:18], "little") not in (2, 3) or
                int.from_bytes(header[18:20], "little") != 62):
            raise SelectionError(f"invalid native x86-64 ELF executable: {path}")


def run_selected_recipes(workspace: Path, manifests: dict, steps: tuple,
                         imported_baseline: dict, *, parent_metadata: dict,
                         publish: bool = False) -> Path | None:
    """Install ordinary packages and native Binutils without file replacement.

    Run native GCC into an isolated staging root, inventory collisions and
    stop before merging GCC or publishing a cross-chroot artifact.
    """
    workspace = Path(workspace).absolute()
    if workspace.is_symlink() or not workspace.is_dir() or workspace.resolve() != workspace:
        raise SelectionError("cross-chroot workspace must be a real directory")
    build, installed = workspace / "build", workspace / "root"
    if not build.is_dir() or build.is_symlink() or not installed.is_dir() or installed.is_symlink():
        raise SelectionError("cross-chroot build and installed roots are required")
    if not steps:
        raise SelectionError("empty cross-chroot selection")
    require_preserved_imports(installed, imported_baseline)
    native_ids = [step.id for step in steps if step.id.startswith("native-")]
    if native_ids and native_ids != ["native-binutils", "native-gcc"]:
        raise SelectionError("native package steps must end with native-binutils then native-gcc")
    staging_root = workspace / "staging"
    if staging_root.exists() or staging_root.is_symlink():
        raise SelectionError("cross-chroot staging root already exists")
    staging_root.mkdir()
    cache = build / "sources"
    cache.mkdir(exist_ok=False)
    (build / "steps").mkdir(exist_ok=False)
    jobs = _host_jobs()
    print(f"[cross-chroot] Recipe runner ready: {len(steps)} steps, make -j{jobs}", flush=True)
    for index, step in enumerate(steps, 1):
        started = time.monotonic()
        prefix = f"[cross-chroot] [{index}/{len(steps)}] {step.id} ({step.version})"
        if step.name not in manifests:
            raise SelectionError(f"missing authoritative manifest: {step.name}")
        stage = staging_root / step.id
        if stage.exists() or stage.is_symlink():
            raise SelectionError(f"staging directory already exists: {step.id}")
        stage.mkdir()
        print(f"{prefix}: fetching and verifying sources", flush=True)
        try:
            source, construction = prepare_step(step, manifests[step.name], build, cache)
            print(f"{prefix}: executing isolated recipe", flush=True)
            run_staged_recipe(
                build, installed, stage, step.recipe,
                source_dir="/work/" + source.relative_to(build).as_posix(),
                build_dir="/work/" + construction.relative_to(build).as_posix(),
                package=step.name, version=step.version, step_id=step.id,
                target=TARGET, jobs=jobs,
            )
            # Exclude the shared generated Info menu before either ordinary
            # ownership preflight or native Binutils collision inventory.
            omit_generated_info_index(stage)
            if step.id == "native-binutils":
                print(f"{prefix}: collecting native collision evidence", flush=True)
                require_preserved_imports(installed, imported_baseline)
                collisions = native_collision_evidence(installed, stage)
                evidence = {
                    "schema_version": 1,
                    "step_id": step.id,
                    "target": TARGET,
                    "version": step.version,
                    "collisions": {
                        name: {"installed": list(prior), "staged": list(candidate)}
                        for name, (prior, candidate) in sorted(collisions.items())
                    },
                }
                report = staging_root / "native-binutils-collisions.json"
                # Exclusive creation prevents replacing previously reviewed evidence.
                with report.open("x", encoding="utf-8") as output:
                    json.dump(evidence, output, sort_keys=True, indent=2)
                    output.write("\n")
                print(
                    f"{prefix}: {len(collisions)} collisions recorded in {report}; "
                    "staged files retained",
                    flush=True,
                )
                if collisions:
                    raise RuntimeError(
                        "native Binutils collisions require ownership review; "
                        "native files were not merged"
                    )
                print(f"{prefix}: checking staged native ELF executables", flush=True)
                verify_native_binutils_structure(stage)
                print(f"{prefix}: preflighting noncolliding native installation", flush=True)
                check_staged_install(installed, stage)
                require_preserved_imports(installed, imported_baseline)
                print(f"{prefix}: merging native Binutils without replacements", flush=True)
                merge_staged_install(installed, stage)
                require_preserved_imports(installed, imported_baseline)
                print(f"{prefix}: checking installed native ELF executables", flush=True)
                verify_native_binutils_structure(installed)
                print(f"{prefix}: native Binutils installed; functional verification pending", flush=True)
                print(f"{prefix}: continuing to staged native GCC diagnostic", flush=True)
                shutil.rmtree(stage)
                print(f"{prefix}: installed ({time.monotonic() - started:.1f}s)", flush=True)
                continue
            if step.id == "native-gcc":
                print(f"{prefix}: verifying merged-/usr staging alias", flush=True)
                omit_native_gcc_staging_lib64_link(stage)
                print(f"{prefix}: collecting native GCC collision evidence", flush=True)
                require_preserved_imports(installed, imported_baseline)
                verify_native_binutils_structure(installed)
                collisions = native_collision_evidence(installed, stage)
                print(f"{prefix}: verifying ten reviewed identical FS-001 entries", flush=True)
                preserved = preserve_reviewed_native_gcc_duplicates(
                    stage, collisions, imported_baseline
                )
                with (staging_root / "native-gcc-preserved-duplicates.json").open(
                    "x", encoding="utf-8"
                ) as output:
                    json.dump({"schema_version": 1, "step_id": step.id,
                               "preserved_imported_entries": preserved}, output,
                              indent=2, sort_keys=True)
                    output.write("\n")
                collisions = native_collision_evidence(installed, stage)
                if set(collisions) != REVIEWED_GCC_DIFFERING:
                    raise SelectionError("native GCC differing collision inventory changed")
                evidence = {
                    "schema_version": 1,
                    "step_id": step.id,
                    "target": TARGET,
                    "version": step.version,
                    "collisions": {
                        name: {"installed": list(prior), "staged": list(candidate)}
                        for name, (prior, candidate) in sorted(collisions.items())
                    },
                }
                report = staging_root / "native-gcc-collisions.json"
                with report.open("x", encoding="utf-8") as output:
                    json.dump(evidence, output, sort_keys=True, indent=2)
                    output.write("\n")
                print(f"{prefix}: {len(collisions)} collisions recorded in {report}", flush=True)
                print(f"{prefix}: constructing isolated GCC candidate root", flush=True)
                candidate_evidence = construct_native_gcc_candidate_root(
                    installed, stage, staging_root, imported_baseline, collisions
                )
                with (staging_root / "native-gcc-candidate-root.json").open(
                    "x", encoding="utf-8"
                ) as output:
                    json.dump(candidate_evidence, output, indent=2, sort_keys=True)
                    output.write("\n")
                require_preserved_imports(installed, imported_baseline)
                print(f"{prefix}: checking native utilities and C/C++ in candidate-only root", flush=True)
                functional = verify_native_gcc_candidate(
                    installed, staging_root / "native-gcc-candidate-root",
                    staging_root, imported_baseline,
                )
                print(f"{prefix}: native candidate functional smoke passed", flush=True)
                print(f"{prefix}: archiving, restoring and rechecking candidate in separate workspace", flush=True)
                verify_native_gcc_relocation(
                    installed, staging_root / "native-gcc-candidate-root",
                    staging_root, imported_baseline,
                )
                print(f"{prefix}: relocated native candidate functional smoke passed", flush=True)
                require_preserved_imports(installed, imported_baseline)
                if not publish:
                    raise RuntimeError(
                        "diagnostic stop after native GCC candidate verification: "
                        "publication disabled in diagnostic mode"
                    )
                from build.bootstrap.cross_chroot_handoff import publish_cross_chroot
                print(f"{prefix}: publishing verified Stage 1C handoff", flush=True)
                result = publish_cross_chroot(
                    workspace, staging_root, staging_root / "native-gcc-candidate-root",
                    steps, parent_metadata,
                )
                print(f"{prefix}: Stage 1C handoff published: {result}", flush=True)
                return result
            if step.id.startswith("native-"):
                raise SelectionError("unsupported native construction step")
            print(f"{prefix}: checking staged installation ownership", flush=True)
            check_staged_install(installed, stage)
            require_preserved_imports(installed, imported_baseline)
            print(f"{prefix}: merging noncolliding files", flush=True)
            merge_staged_install(installed, stage)
            require_preserved_imports(installed, imported_baseline)
        except Exception as exc:
            print(f"{prefix}: FAILED ({exc}); retaining staging for inspection", flush=True)
            raise RuntimeError(f"cross-chroot {step.id} failed: {exc}") from exc
        shutil.rmtree(stage)
        print(f"{prefix}: installed ({time.monotonic() - started:.1f}s)", flush=True)
    # Completion of package installation does not constitute a functional gate.
    print("[cross-chroot] Package installation complete; native verification pending", flush=True)
