"""Cross-toolchain verification contract: sandbox execution and fail-closed behavior."""
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from build.bootstrap.cross_toolchain_verification import (verify_cross_toolchain,
    CrossToolchainVerificationError, CHECK_SCRIPT)

class CrossToolchainVerificationTests(unittest.TestCase):
    def test_target_checks_and_linking_contract(self):
        for item in ('-dumpmachine', '-print-sysroot', 'check.c', 'check.cpp',
                     'check-cxx', 'ELF64', 'X86-64', 'Requesting program interpreter',
                     '$SYSROOT/usr/lib/libc.so.6'):
            self.assertIn(item, CHECK_SCRIPT)

    def test_sandbox_mounts_and_non_execution_of_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            build=base/'build'; root=base/'root'
            build.mkdir();root.mkdir()
            with patch('build.bootstrap.cross_toolchain_verification._base_command', return_value=['bwrap','--clearenv']), \
                 patch('build.bootstrap.cross_toolchain_verification.subprocess.run') as run:
                verify_cross_toolchain(build, root, target='x86_64-distro-linux-gnu')
            args=run.call_args.args[0]
            self.assertIn('--bind', args)
            self.assertIn(str(build), args)
            self.assertIn(str(root), args)
            self.assertEqual(args[-1], 'x86_64-distro-linux-gnu')
            self.assertEqual(run.call_args.kwargs['env'], {'PATH': __import__('os').defpath})

    def test_failed_verification_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);build=base/'build';root=base/'root'
            build.mkdir();root.mkdir()
            with patch('build.bootstrap.cross_toolchain_verification._base_command', return_value=['bwrap']), \
                 patch('build.bootstrap.cross_toolchain_verification.subprocess.run',
                       side_effect=subprocess.CalledProcessError(1,'bwrap', stderr=b'bad target ELF')):
                with self.assertRaisesRegex(CrossToolchainVerificationError, 'bad target ELF'):
                    verify_cross_toolchain(build, root, target='x86_64-distro-linux-gnu')

    def test_invalid_triplet_rejected(self):
        with self.assertRaises(CrossToolchainVerificationError):
            verify_cross_toolchain(Path('/unused'), Path('/unused'), target='x86_64;touch /tmp/bad')

if __name__=='__main__': unittest.main()
