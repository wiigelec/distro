import hashlib
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src/bootstrap'))
from source_artifacts import SourceError, source_spec, verify_detached_signature
from mapping_candidates import candidates

class SourceVerificationTests(unittest.TestCase):
    def test_signed_source_spec(self):
        x = {'artifact': {'url': 'https://upstream.test/pkg.tar.xz',
             'filename': 'pkg.tar.xz', 'signature_url': 'https://upstream.test/pkg.sig',
             'signing_fingerprints': ['A'*40]}}
        self.assertEqual(source_spec(x)['verification_method'], 'detached-openpgp')
    def test_invalid_fingerprint_blocks(self):
        with self.assertRaises(SourceError):
            source_spec({'artifact': {'url': 'https://upstream.test/pkg.tar.xz',
                'filename':'pkg.tar.xz', 'signature_url':'https://upstream.test/a.sig',
                'signing_fingerprints':['BAD']}})
    def test_signature_requires_keyring(self):
        with self.assertRaises(SourceError):
            verify_detached_signature(b'data', b'sig', ['A'*40], keyring=pathlib.Path('/missing-signing-keyring'))
    def test_unapproved_signer_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            keyring=pathlib.Path(td)/'keys.gpg';keyring.write_bytes(b'fixture')
            output=Mock(returncode=0, stdout='[GNUPG:] VALIDSIG ' + 'B'*40 + '\n', stderr='')
            with self.assertRaises(SourceError):
                verify_detached_signature(b'data', b'sig', ['A'*40], keyring=keyring, runner=Mock(return_value=output))
    def test_approved_signer(self):
        with tempfile.TemporaryDirectory() as td:
            keyring=pathlib.Path(td)/'keys.gpg';keyring.write_bytes(b'fixture')
            output=Mock(returncode=0, stdout='[GNUPG:] VALIDSIG ' + 'A'*40 + '\n', stderr='')
            self.assertEqual(verify_detached_signature(b'data', b'sig', ['A'*40], keyring=keyring, runner=Mock(return_value=output)), 'A'*40)
    def test_candidates_are_not_qualified(self):
        report={'commands':{'installed_packages':{'stdout':'gcc 1:16.2.1-2\nglibc 2.44+r50-1\n'}}}
        result=candidates(report,['gcc','glibc','missing'])
        self.assertFalse(result['closure_complete'])
        self.assertEqual(result['packages'][0]['upstream_version_candidate_unverified'],'16.2.1')
        self.assertIsNone(result['packages'][-1]['host_version_observed'])

if __name__=='__main__':unittest.main()
