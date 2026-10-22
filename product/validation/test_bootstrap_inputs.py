"""Offline checks for manifest-driven cross-toolchain source selection."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'bootstrap'))
from bootstrap_inputs import prepare, resolve_sources, checksum_listing
from source_artifacts import SourceError


def manifest():
    return {'schema_version': 1, 'closure_complete': True, 'roots': ['gcc'],
            'packages': [
                {'distro_name': 'binutils', 'host_package': 'binutils',
                 'build_dependencies': [], 'runtime_dependencies': []},
                {'distro_name': 'gcc', 'host_package': 'gcc',
                 'build_dependencies': ['binutils'], 'runtime_dependencies': []}]}


class BootstrapInputsTests(unittest.TestCase):
    def test_declared_packages_only(self):
        versions = {'binutils': '2.47-1', 'gcc': '16.2.0-2', 'extra': '3.1-1'}
        def resolve(record):
            name = record['distro_name']
            return {'status': 'candidate-exact-match', 'mapping_basis': 'exact-release',
                    'upstream': {'name': name, 'version': '1.0',
                                 'artifact_url': f'https://example.org/{name}-1.0.tar.xz'}}
        with patch('bootstrap_inputs.resolve_package', side_effect=resolve), \
                patch('bootstrap_inputs.checksum_listing', return_value=('https://example.org/SHA256SUMS', 'sha256')):
            result = resolve_sources(manifest(), versions)
        self.assertEqual([p['distro_name'] for p in result['packages']], ['binutils', 'gcc'])

    def test_kernel_signed_checksum_listing(self):
        digest = 'a' * 64
        armored = ('-----BEGIN PGP SIGNED MESSAGE-----\n'
                   'Hash: SHA256\n\n'
                   + digest + '  linux-7.2.11.tar.gz\n'
                   '-----BEGIN PGP SIGNATURE-----\n'
                   'signature\n-----END PGP SIGNATURE-----\n').encode()
        def fetch(url, *, limit):
            if url.endswith('/sha256sums.asc'):
                return armored
            raise OSError('not published')
        self.assertEqual(
            checksum_listing('https://cdn.kernel.org/pub/linux/kernel/v7.x/linux-7.2.11.tar.gz',
                             'linux-7.2.11.tar.gz', fetch),
            ('https://cdn.kernel.org/pub/linux/kernel/v7.x/sha256sums.asc', 'sha256'))

    def test_missing_declared_host_blocks(self):
        with self.assertRaisesRegex(SourceError, 'unavailable'):
            resolve_sources(manifest(), {'binutils': '2.47-1'})

    def test_missing_dependency_blocks(self):
        doc = manifest()
        doc['packages'][0]['build_dependencies'] = ['not-declared']
        with self.assertRaisesRegex(ValueError, 'unresolved dependency'):
            resolve_sources(doc, {'binutils': '2.47-1', 'gcc': '16.2.0-2'})

    def test_resume_rejects_changed_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest_path = root / 'manifest.json'
            data = manifest()
            manifest_path.write_text(json.dumps(data))
            project = root / 'project'
            state = project / '.distro-bootstrap'
            state.mkdir(parents=True)
            (state / 'baseline.json').write_text('{}')
            with self.assertRaisesRegex(SourceError, 'manifest changed'):
                prepare(project, manifest_path)


if __name__ == '__main__':
    unittest.main()
