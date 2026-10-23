"""FS-001 M2 host cross-build CLI dispatch regression checks."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "product/scripts/build"


class TemporaryToolsCliTests(unittest.TestCase):
    def test_temp_tools_help_loads_runner(self):
        # argparse --help alone exits before host_build is imported; exercise
        # the real execution branch with a missing input instead.
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory) / "root"
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


if __name__ == "__main__":
    unittest.main()
