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

    def test_expired_unrelated_key_does_not_invalidate_good_signature(self):
        output = ('[GNUPG:] NEWSIG\n'
                  '[GNUPG:] KEYEXPIRED 1647984997\n'
                  '[GNUPG:] KEYEXPIRED 1542410123\n'
                  '[GNUPG:] GOODSIG DC2B16215ED5412A signer\n'
                  '[GNUPG:] VALIDSIG ' + APPROVED +
                  ' 2026-07-25 1784937664 0 4 0 1 8 00 ' + '35B17DF5752577CA0C541CEB94BFDF4484AD142F' + '\n'
                  '[GNUPG:] KEYEXPIRED 1668019939\n'
                  '[GNUPG:] TRUST_UNDEFINED 0 pgp\n')
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, output, ''))
        self.assertEqual(verify_detached_signature(b'archive', b'sig', [APPROVED],
                                                  runner=runner), APPROVED)

    def test_expired_signing_key_fails_if_gpg_returns_error(self):
        output = ('[GNUPG:] VALIDSIG ' + APPROVED + ' 2026 0 0 0 0 0 0\n'
                  '[GNUPG:] KEYEXPIRED 1647984997\n')
        runner = Mock(return_value=subprocess.CompletedProcess([], 1, output, ''))
        with self.assertRaises(SourceError):
            verify_detached_signature(b'archive', b'sig', [APPROVED], runner=runner)

    def test_bad_signature_status_rejected(self):
        output = ('[GNUPG:] VALIDSIG ' + APPROVED + ' 2026 0 0 0 0 0 0\n'
                  '[GNUPG:] BADSIG DC2B16215ED5412A signer\n')
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, output, ''))
        with self.assertRaises(SourceError):
            verify_detached_signature(b'archive', b'sig', [APPROVED], runner=runner)

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
