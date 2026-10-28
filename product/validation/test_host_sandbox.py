"""Initial unit checks for FS-001 sandbox command construction.

These are Build development tests, not yet active requirement bindings.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from build.host_sandbox import SandboxError, recipe_command, run_recipe


class HostSandboxTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.work = root / "build"
        self.root = root / "root"
        self.work.mkdir()
        self.root.mkdir()
        self.recipe = root / "recipe.sh"
        self.recipe.write_text("#!/bin/bash\ntrue\n")
        self.args = (self.work, self.root, self.recipe)
        self.kwargs = dict(source_dir="/work/gcc/source", build_dir="/work/gcc/build",
                           package="gcc", version="16.2.0", step_id="gcc-pass1")

    @patch("build.host_sandbox.shutil.which", return_value="/usr/bin/bwrap")
    def test_mounts_and_environment(self, _):
        c = recipe_command(*self.args, **self.kwargs)
        self.assertIn("--unshare-net", c)
        self.assertIn("--unshare-user", c)
        self.assertIn("--clearenv", c)
        self.assertEqual(c[-2:], ["/bin/bash", "/recipe.sh"])
        self.assertEqual(c[c.index("--bind") + 2], "/work")
        self.assertNotIn("--dev-bind", c)
        self.assertIn("/toolchain/tools/bin:/usr/bin:/bin", c)
        self.assertNotIn("LD_LIBRARY_PATH", c)

    @patch("build.host_sandbox.shutil.which", return_value=None)
    def test_missing_bwrap_fails_closed(self, _):
        with self.assertRaises(SandboxError):
            run_recipe(*self.args, **self.kwargs)

    @patch("build.host_sandbox.shutil.which", return_value="/usr/bin/bwrap")
    def test_reject_nonwork_source(self, _):
        with self.assertRaises(SandboxError):
            recipe_command(*self.args, **{**self.kwargs, "source_dir": "/etc"})

    @patch("build.host_sandbox.shutil.which", return_value="/usr/bin/bwrap")
    def test_distinct_work_and_root(self, _):
        with self.assertRaises(SandboxError):
            recipe_command(self.work, self.work, self.recipe, **self.kwargs)


if __name__ == "__main__":
    unittest.main()
