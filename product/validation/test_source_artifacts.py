"""Negative and restart tests for verified source acquisition."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from preflight import qualified_baseline
from source_artifacts import SourceError, expected_checksum, select_component, verify_and_lock


ARCHIVE = b'fixture upstream archive\n'
DIGEST = hashlib.sha256(ARCHIVE).hexdigest()
RECIPE_SHA256 = hashlib.sha256(b'recipe').hexdigest()


def baseline():
    inventory = {'schema_version': 1, 'closure_complete': True, 'roots': ['compiler'],
                 'packages': [{'distro_name': 'compiler', 'host_package': 'gcc',
                               'build_dependencies': [], 'runtime_dependencies': [],
                               'upstream': {'name': 'gcc', 'version': '15.1.0',
                                            'official_url': 'https://gcc.gnu.org/',
                                            'mapping_basis': 'reviewed',
                                            'artifact': {'url': 'https://gcc.gnu.org/gcc.tar.xz',
                                                         'checksum_url': 'https://gcc.gnu.org/SHA256SUMS',
                                                         'filename': 'gcc.tar.xz',
                                                         'checksum_algorithm': 'sha256'}}}]}
    return qualified_baseline(inventory, {'gcc': '15.1.0-1'})


def fetch(url, *, limit):
    if url.endswith('SHA256SUMS'):
        return f'{DIGEST}  gcc.tar.xz\n'.encode()
    return ARCHIVE


class SourceTests(unittest.TestCase):
    def test_exact_checksum(self):
        self.assertEqual(expected_checksum(f'{DIGEST} *gcc.tar.xz\n'.encode(), 'gcc.tar.xz', 'sha256'), DIGEST)

    def test_ambiguous_checksum(self):
        with self.assertRaises(SourceError):
            expected_checksum(f'{DIGEST} gcc.tar.xz\n{DIGEST} gcc.tar.xz\n'.encode(), 'gcc.tar.xz', 'sha256')

    def test_frozen_lock_and_offline_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache, locks = Path(tmp) / 'cache', Path(tmp) / 'locks'
            first = verify_and_lock(baseline(), 'compiler', cache, locks, recipe_sha256=RECIPE_SHA256, fetch=fetch)
            again = verify_and_lock(baseline(), 'compiler', cache, locks, recipe_sha256=RECIPE_SHA256, offline=True)
            self.assertEqual(first, again)

    def test_tampered_cached_bytes_block_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache, locks = Path(tmp) / 'cache', Path(tmp) / 'locks'
            verify_and_lock(baseline(), 'compiler', cache, locks, recipe_sha256=RECIPE_SHA256, fetch=fetch)
            (cache / 'compiler-gcc.tar.xz').write_bytes(b'altered')
            with self.assertRaises(SourceError):
                verify_and_lock(baseline(), 'compiler', cache, locks, recipe_sha256=RECIPE_SHA256, offline=True)

    def test_unlocked_offline_source_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SourceError):
                verify_and_lock(baseline(), 'compiler', Path(tmp) / 'cache', Path(tmp) / 'locks', recipe_sha256=RECIPE_SHA256, offline=True)

    def test_changed_recipe_blocks_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache, locks = Path(tmp) / 'cache', Path(tmp) / 'locks'
            verify_and_lock(baseline(), 'compiler', cache, locks, recipe_sha256=RECIPE_SHA256, fetch=fetch)
            with self.assertRaises(SourceError):
                verify_and_lock(baseline(), 'compiler', cache, locks, recipe_sha256='f'*64, offline=True)

    def test_changed_baseline_blocks_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache, locks = Path(tmp) / 'cache', Path(tmp) / 'locks'
            verify_and_lock(baseline(), 'compiler', cache, locks, recipe_sha256=RECIPE_SHA256, fetch=fetch)
            altered = baseline(); altered['packages'][0]['host_version']['pkgrel'] = '2'
            with self.assertRaises(SourceError):
                verify_and_lock(altered, 'compiler', cache, locks, recipe_sha256=RECIPE_SHA256, offline=True)

    def test_modified_download_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            def bad(url, *, limit):
                return fetch(url, limit=limit) if url.endswith('SHA256SUMS') else b'modified'
            with self.assertRaises(SourceError):
                verify_and_lock(baseline(), 'compiler', Path(tmp) / 'cache', Path(tmp) / 'locks', recipe_sha256=RECIPE_SHA256, fetch=bad)
            self.assertFalse((Path(tmp) / 'locks').exists())

    def test_signature_source_cannot_downgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = baseline(); doc['packages'][0]['upstream']['signature_url'] = 'https://gcc.gnu.org/test.sig'
            # The baseline checksum is now invalid; either condition fails closed.
            with self.assertRaises(SourceError):
                verify_and_lock(doc, 'compiler', Path(tmp) / 'cache', Path(tmp) / 'locks', recipe_sha256=RECIPE_SHA256, fetch=fetch)

    def test_missing_package_blocked(self):
        with self.assertRaises(SourceError):
            select_component(baseline(), 'missing')


if __name__ == '__main__':
    unittest.main()
