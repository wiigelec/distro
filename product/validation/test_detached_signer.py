"""Detached release signature verification with approved signer identity."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'bootstrap'))
from source_artifacts import SourceError, verify_detached_signature

APPROVED = 'FD19E6D31B192EE4DC63EAD3DC2B16215ED5412A'


class DetachedSignatureTests(unittest.TestCase):
    def result(self, fingerprint=APPROVED, code=0):
        return subprocess.CompletedProcess([], code,
            '[GNUPG:] GOODSIG 0000000000000000 signer\n'
            '[GNUPG:] VALIDSIG ' + fingerprint + ' 2026 0 0 0 0 0 0\n', '')

    def test_default_uses_gpg_with_existing_keyring(self):
        runner = Mock(return_value=self.result())
        self.assertEqual(verify_detached_signature(b'archive', b'sig', [APPROVED],
                                                  runner=runner), APPROVED)
        cmd = runner.call_args.args[0]
        self.assertEqual(cmd[:2], ['gpg', '--batch'])
        self.assertIn('--verify', cmd)

    def test_unapproved_signer_rejected(self):
        runner = Mock(return_value=self.result('A' * 40))
        with self.assertRaises(SourceError):
            verify_detached_signature(b'archive', b'sig', [APPROVED], runner=runner)

    def test_invalid_signature_rejected(self):
        runner = Mock(return_value=self.result(code=1))
        with self.assertRaises(SourceError):
            verify_detached_signature(b'archive', b'sig', [APPROVED], runner=runner)


if __name__ == '__main__':
    unittest.main()
