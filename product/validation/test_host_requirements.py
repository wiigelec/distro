"""Pure host-version and preflight ordering tests, runnable outside Linux."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from build.host_requirements import _version, _at_least, qualify_host, HostRequirementsError, _check_tools, _check_native_compilers
from build.bootstrap.cross_toolchain import run_stage


class HostQualificationTests(unittest.TestCase):
    def test_version_floor_and_suffix(self):
        self.assertTrue(_at_least('GNU Make 4.4.1', '4.0'))
        self.assertTrue(_at_least('grep (GNU grep) 2.5.1a', '2.5.1a'))
        self.assertFalse(_at_least('GNU grep 2.5.1', '2.5.1a'))
        self.assertFalse(_at_least('GNU tar 1.21', '1.22'))
        self.assertTrue(_at_least('Linux 6.12.4-arch1-1', '5.10'))
        with self.assertRaises(HostRequirementsError):
            _version('unknown version')

    def test_wrong_architecture_fails_before_commands(self):
        with patch('build.host_requirements.platform.system', return_value='Linux'), \
             patch('build.host_requirements.platform.machine', return_value='aarch64'), \
             patch('build.host_requirements._check_tools') as tools:
            with self.assertRaises(HostRequirementsError): qualify_host()
            tools.assert_not_called()

    def test_qualification_failure_does_not_mutate_workspace(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('build.bootstrap.cross_toolchain.sys.platform', 'linux'), \
             patch('build.bootstrap.cross_toolchain.qualify_host', side_effect=HostRequirementsError('missing make')), \
             patch('build.bootstrap.cross_toolchain.probe_bubblewrap') as sandbox:
            with self.assertRaises(HostRequirementsError): run_stage(Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])
            sandbox.assert_not_called()

    def test_banner_does_not_use_later_version_lines(self):
        # A library version printed later must not qualify an older tool.
        with patch('build.host_requirements.MINIMUMS', {'make': ('make', '4.0')}), \
             patch('build.host_requirements.shutil.which', return_value='/usr/bin/make'), \
             patch('build.host_requirements.Path.resolve', return_value=Path('/usr/bin/make')), \
             patch('build.host_requirements.Path.is_file', return_value=True), \
             patch('build.host_requirements._capture', return_value='GNU Make 3.8\nGNU libc 9.9'):
            with self.assertRaisesRegex(HostRequirementsError, 'below required'):
                _check_tools()

    def test_compilers_use_qualified_resolved_command_path(self):
        commands = []
        def capture(args):
            commands.append(args)
            if '-dumpmachine' in args: return 'x86_64-pc-linux-gnu'
            if len(args) == 1: return 'host-c-ok' if args[0].endswith('/probe') else ''
            return ''
        # Compiler invocation is tested without actually running a host compiler.
        with patch('build.host_requirements.shutil.which', side_effect=lambda name, **kw: '/bin/' + name), \
             patch('build.host_requirements._capture', side_effect=capture):
            with self.assertRaises(HostRequirementsError):
                _check_native_compilers()
        self.assertEqual(commands[0], ['/bin/gcc', '-dumpmachine'])

    def test_tool_checks_use_minimums(self):
        from build.host_requirements import MINIMUMS
        self.assertEqual(MINIMUMS['gcc'][1], '5.4')
        self.assertEqual(MINIMUMS['xz'][1], '5.0.0')
        self.assertIn('texinfo', MINIMUMS)


if __name__ == '__main__': unittest.main()
