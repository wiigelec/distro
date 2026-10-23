"""Integration coverage for complete inventory qualification."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from preflight import PreflightError, qualified_baseline


def inventory():
    return {'schema_version': 1, 'closure_complete': True, 'roots': ['compiler'], 'packages': [
        {'distro_name': 'compiler', 'host_package': 'gcc', 'build_dependencies': ['libc'],
         'runtime_dependencies': ['libc'], 'upstream': {'name': 'gcc', 'version': '15.1.0',
          'official_url': 'https://gcc.gnu.org/', 'mapping_basis': 'reviewed source mapping', 'artifact': {'url': 'https://example.org/source.tar.xz', 'checksum_url': 'https://example.org/checksums', 'filename': 'source.tar.xz', 'checksum_algorithm': 'sha256'}}},
        {'distro_name': 'libc', 'host_package': 'glibc', 'build_dependencies': [],
         'runtime_dependencies': [], 'upstream': {'name': 'glibc', 'version': '2.40',
          'official_url': 'https://www.gnu.org/software/libc/', 'mapping_basis': 'reviewed source mapping', 'artifact': {'url': 'https://example.org/source.tar.xz', 'checksum_url': 'https://example.org/checksums', 'filename': 'source.tar.xz', 'checksum_algorithm': 'sha256'}}}]}


class PreflightTests(unittest.TestCase):
    def test_complete_inventory(self):
        result = qualified_baseline(inventory(), {'gcc': '1:15.1.0-2', 'glibc': '2.40-1'})
        self.assertEqual(result['closure_summary']['packages'], ['compiler', 'libc'])
        self.assertEqual(result['packages'][0]['host_version']['full'], '1:15.1.0-2')

    def test_incomplete_manifest(self):
        doc = inventory(); doc['closure_complete'] = False
        with self.assertRaises(PreflightError):
            qualified_baseline(doc, {'gcc': '15.1.0-2', 'glibc': '2.40-1'})

    def test_unmapped_dependency(self):
        doc = inventory(); doc['packages'][1]['host_package'] = 'missing'
        with self.assertRaises(PreflightError):
            qualified_baseline(doc, {'gcc': '15.1.0-2', 'glibc': '2.40-1'})

    def test_unknown_edge(self):
        doc = inventory(); doc['packages'][1]['runtime_dependencies'] = ['unknown']
        with self.assertRaises(PreflightError):
            qualified_baseline(doc, {'gcc': '15.1.0-2', 'glibc': '2.40-1'})

    def test_dependency_change_affects_baseline(self):
        doc = inventory(); orig = qualified_baseline(doc, {'gcc': '15.1.0-2', 'glibc': '2.40-1'})
        doc['packages'][0]['runtime_dependencies'] = []
        changed = qualified_baseline(doc, {'gcc': '15.1.0-2', 'glibc': '2.40-1'})
        self.assertNotEqual(orig['baseline_sha256'], changed['baseline_sha256'])

    def test_host_version_change_affects_baseline(self):
        doc = inventory(); a = qualified_baseline(doc, {'gcc': '15.1.0-2', 'glibc': '2.40-1'})
        b = qualified_baseline(doc, {'gcc': '15.1.0-3', 'glibc': '2.40-1'})
        self.assertNotEqual(a['baseline_sha256'], b['baseline_sha256'])


if __name__ == '__main__':
    unittest.main()
