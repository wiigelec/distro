"""Live console output must also be preserved in M2 package logs."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

BOOTSTRAP = Path(__file__).resolve().parents[1] / 'src' / 'bootstrap'
sys.path.insert(0, str(BOOTSTRAP))
from temporary_tools.temp_cross_package import run


class ConsoleProgressTests(unittest.TestCase):
    def test_stdout_and_stderr_are_streamed_and_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'build.log'
            code = ('import sys; sys.stdout.write("configuring\\n"); '
                    'sys.stdout.flush(); sys.stderr.write("warning\\n")')
            class Capture:
                def __init__(self):
                    self.buffer = io.BytesIO()
            capture = Capture()
            with mock.patch.object(sys, 'stdout', capture):
                run([sys.executable, '-c', code], log, timeout=10)
            output = capture.buffer.getvalue()
            self.assertIn(b'configuring', output)
            self.assertIn(b'warning', output)
            self.assertIn(b'configuring', log.read_bytes())
            self.assertIn(b'warning', log.read_bytes())
            self.assertIn(b'STEP ', log.read_bytes())

    def test_failure_retains_output_and_identifies_log(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'failure.log'
            class Capture:
                def __init__(self):
                    self.buffer = io.BytesIO()
            with mock.patch.object(sys, 'stdout', Capture()):
                with self.assertRaisesRegex(RuntimeError, r'command failed \(7\)') as error:
                    run([sys.executable, '-c',
                         'import sys; print("build failed"); sys.exit(7)'], log, timeout=10)
            self.assertIn(str(log), str(error.exception))
            self.assertIn(b'build failed', log.read_bytes())

    def test_timeout_terminates_quiet_child(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'timeout.log'
            with self.assertRaises(subprocess.TimeoutExpired):
                run([sys.executable, '-c', 'import time; time.sleep(10)'], log, timeout=0.1)


if __name__ == '__main__':
    unittest.main()
