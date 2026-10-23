"""No-network failure-path checks for bootstrap execution prerequisites."""
import unittest
from unittest.mock import patch

from host_checks import HostCheckError, qualify_source_availability


class HostChecksTests(unittest.TestCase):
    def test_missing_source_is_blocking(self):
        data = [{'distro_name': 'example', 'upstream': {'artifact': {
            'url': 'https://example.org/pkg.tar.xz', 'filename': 'pkg.tar.xz',
            'checksum_url': 'https://example.org/SHA256SUMS',
            'checksum_algorithm': 'sha256'}}}]
        with patch('host_checks.assert_resource_available', side_effect=HostCheckError('missing')):
            with self.assertRaisesRegex(HostCheckError, 'example: missing'):
                qualify_source_availability(data)

    def test_missing_checksum_entry_blocks(self):
        data = [{'distro_name': 'example', 'upstream': {'artifact': {
            'url': 'https://example.org/pkg.tar.xz', 'filename': 'pkg.tar.xz',
            'checksum_url': 'https://example.org/SHA256SUMS',
            'checksum_algorithm': 'sha256'}}}]
        with patch('host_checks.assert_resource_available'), patch('host_checks.read_https', return_value=b''):
            with self.assertRaisesRegex(HostCheckError, 'example:'):
                qualify_source_availability(data)


if __name__ == '__main__':
    unittest.main()
