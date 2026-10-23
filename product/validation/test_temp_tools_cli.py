"""FS-001 M2 host cross-build CLI dispatch regression checks."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "product/scripts/build"


class TemporaryToolsCliTests(unittest.TestCase):
    def test_temp_tools_workspace_path_reaches_m1_resolution(self):
        # argparse --help alone exits before host_build is imported; exercise
        # the real execution branch with a missing input instead.
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory) / "workspace"
            result = subprocess.run(
                [sys.executable, str(ENTRYPOINT), "temp-tools",
                 "--root", str(project_root),
                 "--cross-toolchain", str(Path(directory) / "missing-m1")],
                capture_output=True, text=True, timeout=30,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("ModuleNotFoundError", result.stderr)
        self.assertNotIn("ImportError", result.stderr)
        self.assertIn("missing-m1", result.stderr)

    def test_host_build_passes_workspace_unchanged(self):
        from unittest.mock import patch
        sys.path.insert(0, str(ROOT / "product/src"))
        try:
            from bootstrap.temporary_tools import host_build
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "build"
            archive = Path(directory) / "cross-toolchain-root.tar.xz"
            with patch.object(host_build.os, "geteuid", return_value=1000), \
                    patch.object(host_build, "build_temporary_tools", return_value=0) as run:
                rc = host_build.main(["--root", str(workspace),
                                      "--cross-toolchain", str(archive)])
            self.assertEqual(rc, 0)
            run.assert_called_once_with(workspace, archive)


if __name__ == "__main__":
    unittest.main()
