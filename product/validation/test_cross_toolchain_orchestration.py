"""Unit tests for cross-toolchain orchestration without downloads or Linux sandbox."""
import hashlib
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from build.bootstrap.cross_toolchain import selected_steps, prepare_step, run_stage
from build.selection import SelectionError


def archive(path, label):
    with tarfile.open(path, "w:xz") as t:
        content = b"test source"
        info = tarfile.TarInfo(label + "/README")
        info.size = len(content)
        t.addfile(info, io.BytesIO(content))
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BootstrapStageTests(unittest.TestCase):
    def test_stage_paths_resolve_and_selection_order(self):
        ms, steps = selected_steps()
        self.assertEqual([s.id for s in steps], ["binutils-pass1", "gcc-pass1", "linux-headers", "glibc", "gcc-libstdcpp"])
        self.assertTrue(all(s.recipe.is_file() for s in steps))
        self.assertEqual(set(ms), {"binutils", "gcc", "linux", "glibc"})

    def test_fresh_independent_gcc_extractions_and_supplements(self):
        ms, steps = selected_steps()
        gcc1, gcc2 = steps[1], steps[4]
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); build = base / "build"; cache = build / "sources"
            build.mkdir(); cache.mkdir()
            archive_file = base / "gcc.tar.xz"
            gcc_digest = archive(archive_file, "gcc-16.2.0")
            supplement_files = {}
            for name in ("gmp", "mpfr", "mpc"):
                file = base / (name + ".tar.xz")
                supplement_files[name] = (file, archive(file, name))
            from dataclasses import replace
            gcc1 = replace(gcc1, checksum=gcc_digest,
                           supplements={name: ("1", digest) for name, (_, digest) in supplement_files.items()})
            gcc2 = replace(gcc2, checksum=gcc_digest)
            def fake_fetch(src, version, destination, checksum):
                src_path = archive_file if checksum == gcc_digest else next(f for f, d in supplement_files.values() if d == checksum)
                destination.write_bytes(src_path.read_bytes())
                return destination
            with patch("build.bootstrap.cross_toolchain.fetch_verified", side_effect=fake_fetch):
                one, _ = prepare_step(gcc1, ms["gcc"], build, cache)
                two, _ = prepare_step(gcc2, ms["gcc"], build, cache)
            self.assertNotEqual(one, two)
            self.assertEqual((one / "README").read_bytes(), (two / "README").read_bytes())
            self.assertEqual({p.name for p in one.iterdir()}, {"README", "gmp", "mpfr", "mpc"})
            self.assertEqual({p.name for p in two.iterdir()}, {"README"})
            with self.assertRaises(SelectionError):
                prepare_step(gcc1, ms["gcc"], build, cache)

    def test_non_linux_rejected_before_workspace_mutation(self):
        with tempfile.TemporaryDirectory() as tmp, patch("build.bootstrap.cross_toolchain.sys.platform", "cygwin"):
            with self.assertRaises(RuntimeError):
                run_stage(Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_failed_isolation_rejected_before_workspace_mutation(self):
        with tempfile.TemporaryDirectory() as tmp, patch("build.bootstrap.cross_toolchain.sys.platform", "linux"), patch("build.bootstrap.cross_toolchain.probe_bubblewrap", side_effect=RuntimeError("no bwrap")):
            with self.assertRaises(RuntimeError):
                run_stage(Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
