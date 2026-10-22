"""Failure isolation and evidence handling for cross-toolchain projects."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bootstrap'))
import project_build
from cross_toolchain import ToolchainError


class ProjectSafetyTests(unittest.TestCase):
    def test_incomplete_stage_is_not_retried_over_dirty_root(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            baseline = {'baseline_sha256': '1'*64}
            state = project / '.distro-bootstrap'
            stale = state / 'work' / 'cross-toolchain' / 'binutils'
            stale.mkdir(parents=True)
            (stale / 'build.log').write_text('failed installation')
            with patch.object(project_build, 'source_requirements'), \
                 patch.object(project_build, 'initialize_root'), \
                 patch.object(project_build, 'run_stage', side_effect=AssertionError('must not run')):
                with self.assertRaisesRegex(ToolchainError, 'fresh build directory'):
                    project_build.build(project, baseline)
            self.assertEqual((stale / 'build.log').read_text(), 'failed installation')


if __name__ == '__main__':
    unittest.main()
