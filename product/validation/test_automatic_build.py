"""Construction source mapping and immutable execution state."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'bootstrap'))
import automatic_build as subject


class ConstructionInputTests(unittest.TestCase):
    def sample(self):
        entries = []
        for name, version in [('binutils', '2.47-4'),
                              ('gcc', '16.2.1+r23+gd564253eb6c8-1'),
                              ('linux', '7.2.11.arch1-1'), ('glibc', '2.43-1')]:
            upstream = {'name': name, 'version': version.rsplit('-', 1)[0],
                        'filename': name + '.tar.xz',
                        'artifact_url': 'https://example.org/' + name + '.tar.xz'}
            if name == 'linux':
                upstream['version'] = '7.2.11'
            if name == 'gcc':
                upstream['revision'] = 'd564253eb6c859e266d3cae18e82fb4db9a88316'
            entries.append({'distro_name': name, 'host_package_candidate': name,
                            'host_version_observed': version,
                            'upstream_discovery': {'status': 'candidate-exact-match',
                                                   'mapping_basis': 'observed',
                                                   'upstream': upstream}})
        return {'manifest_sha256': '0' * 64, 'packages': entries}

    @patch.object(subject, 'locate_checksum', return_value=('https://example.org/sha512.sum', 'sha512'))
    def test_release_mapping_and_kernel_header_source(self, locator):
        output = subject.make_baseline(self.sample(), {'packages': []})
        versions = {r['distro_name']: r['upstream']['version'] for r in output['packages']}
        self.assertEqual(versions['gcc'], '16.2.0')
        self.assertEqual(versions['linux-api-headers'], '7.2.11')
        self.assertEqual(len(output['packages']), 4)
        self.assertEqual(output['baseline_sha256'], subject.canonical_digest(
            {k: v for k, v in output.items() if k != 'baseline_sha256'}))
        self.assertEqual(locator.call_count, 4)

    def test_missing_official_checksum_blocks(self):
        with patch.object(subject, 'locate_checksum', side_effect=subject.SourceError('missing')):
            with self.assertRaises(subject.SourceError):
                subject.make_baseline(self.sample(), {'packages': []})

    def test_saved_execution_is_immutable(self):
        with tempfile.TemporaryDirectory() as dirname:
            target = Path(dirname) / 'baseline.json'
            subject.save_once(target, {'id': 1})
            subject.save_once(target, {'id': 1})
            with self.assertRaises(subject.SourceError):
                subject.save_once(target, {'id': 2})


if __name__ == '__main__':
    unittest.main()
