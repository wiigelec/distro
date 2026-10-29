"""Build CLI dispatch and fail-closed preflight tests."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from build.cli import main


class BuildCliTests(unittest.TestCase):
    def test_host_check_does_not_mutate_workspace_or_invoke_build(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("build.cli.sys.platform", "linux"), \
             patch("build.cli.selected_steps") as selected, \
             patch("build.cli.qualify_host") as host, \
             patch("build.cli.probe_bubblewrap") as sandbox, \
             patch("build.cli.run_stage") as build:
            with contextlib.redirect_stdout(io.StringIO()):
                result = main(["cross-toolchain", "--check-host", "--root", tmp])
            self.assertEqual(result, 0)
            selected.assert_called_once_with()
            host.assert_called_once_with()
            sandbox.assert_called_once_with()
            build.assert_not_called()
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_wrong_host_does_not_call_preflight(self):
        with patch("build.cli.sys.platform", "cygwin"), \
             patch("build.cli.qualify_host") as host, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["cross-toolchain", "--check-host"]), 1)
            host.assert_not_called()

    def test_preflight_failure_does_not_dispatch(self):
        with patch("build.cli.sys.platform", "linux"), \
             patch("build.cli.selected_steps"), \
             patch("build.cli.qualify_host", side_effect=RuntimeError("missing tool")), \
             patch("build.cli.probe_bubblewrap") as sandbox, \
             patch("build.cli.run_stage") as build, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["cross-toolchain", "--check-host"]), 1)
            sandbox.assert_not_called()
            build.assert_not_called()

    def test_build_mode_dispatch_and_never_claim_success(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("build.cli.run_stage") as build, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["cross-toolchain", "--root", tmp]), 1)
            build.assert_called_once_with(Path(tmp))

    def test_build_failure_reports_nonzero(self):
        with patch("build.cli.run_stage", side_effect=RuntimeError("unimplemented handoff")), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["cross-toolchain", "--root", "/unused"]), 1)


if __name__ == "__main__":
    unittest.main()
