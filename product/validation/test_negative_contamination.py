"""Exercise the actual target inspector with a deliberately polluted compiler invocation."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bootstrap'))
from cross_toolchain import TARGET, ToolchainError, inspect_target


class ContaminationTests(unittest.TestCase):
    def test_negative_probe_is_part_of_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            root = folder / 'root'
            work = folder / 'work'
            work.mkdir()
            for rel in (f'usr/bin/{TARGET}-gcc', f'usr/bin/{TARGET}-g++',
                        f'bin/{TARGET}-as', f'bin/{TARGET}-ld',
                        'lib64/ld-linux-x86-64.so.2'):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            calls = []

            def runner(argv, **kwargs):
                calls.append(argv)
                if '-dumpmachine' in argv:
                    return subprocess.CompletedProcess(argv, 0, TARGET + '\n', '')
                if '-print-search-dirs' in argv:
                    return subprocess.CompletedProcess(argv, 0, 'install: /toolchain/usr/lib\n', '')
                if '-Wp,-v' in argv:
                    path = '/usr/include' if '-I/usr/include' in argv else '/toolchain/usr/include'
                    output = '#include <...> search starts here:\n ' + path + '\nEnd of search list.\n'
                    return subprocess.CompletedProcess(argv, 0, '', output)
                if '-print-file-name=crt1.o' in argv:
                    # The test stops here after exercising the negative probe.
                    raise RuntimeError('startup reached')
                raise AssertionError('unexpected command: ' + repr(argv))

            with patch('cross_toolchain.sandbox_command',
                       side_effect=lambda work, root, argv: argv):
                with self.assertRaisesRegex(RuntimeError, 'startup reached'):
                    inspect_target(root, work, runner=runner)
            self.assertEqual(sum('-I/usr/include' in cmd for cmd in calls), 1)

    def test_negative_probe_fails_when_contamination_is_not_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            root = folder / 'root'
            work = folder / 'work'
            work.mkdir()
            for rel in (f'usr/bin/{TARGET}-gcc', f'usr/bin/{TARGET}-g++',
                        f'bin/{TARGET}-as', f'bin/{TARGET}-ld',
                        'lib64/ld-linux-x86-64.so.2'):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()

            def runner(argv, **kwargs):
                if '-dumpmachine' in argv:
                    return subprocess.CompletedProcess(argv, 0, TARGET + '\n', '')
                if '-print-search-dirs' in argv:
                    return subprocess.CompletedProcess(argv, 0, 'install: /toolchain/usr/lib\n', '')
                if '-Wp,-v' in argv:
                    output = '#include <...> search starts here:\n /toolchain/usr/include\nEnd of search list.\n'
                    return subprocess.CompletedProcess(argv, 0, '', output)
                raise AssertionError('negative test must fail before link')

            with patch('cross_toolchain.sandbox_command',
                       side_effect=lambda work, root, argv: argv):
                with self.assertRaisesRegex(ToolchainError, 'negative contamination probe was not rejected'):
                    inspect_target(root, work, runner=runner)


if __name__ == '__main__':
    unittest.main()
