"""Host audit owns upstream discovery in the same report and command."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import runpy

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'build'
SRC = Path(__file__).resolve().parents[1] / 'src' / 'bootstrap'
sys.path.insert(0, str(SRC))


class HostAuditDiscoveryTests(unittest.TestCase):
    def test_combined_report(self):
        module = runpy.run_path(str(SCRIPT), run_name='host_audit_test')
        manifest = {'schema_version': 1, 'packages': [{'distro_name': 'make'}]}
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            selected = base / 'manifest.json'
            report = base / 'report.json'
            selected.write_text(json.dumps(manifest))
            with patch.dict(module['main'].__globals__, {
                'installed_arch_packages': lambda: {'make': '4.4.1-3'},
                'discover_from_audit': lambda audit: {
                    'packages': [{'distro_name': 'make', 'status': 'candidate-exact-match',
                                  'upstream': {'name': 'make', 'version': '4.4.1'}}],
                    'summary': {'matched': 1, 'unresolved': 0}, 'note': 'candidate only'},
            }):
                self.assertEqual(module['main'](['host-audit', '--manifest', str(selected),
                                                 '--out', str(report)]), 0)
            result = json.loads(report.read_text())
            self.assertEqual(result['source_summary']['matched'], 1)
            self.assertEqual(result['packages'][0]['upstream_discovery']['upstream']['version'], '4.4.1')

    def test_no_separate_source_command(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), '--help'],
                              text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn('source-discover', proc.stdout)


if __name__ == '__main__':
    unittest.main()
