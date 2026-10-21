"""Dynamic upstream discovery is host-led and fails closed on ambiguity."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src' / 'bootstrap' / 'upstream_discovery.py'
spec = importlib.util.spec_from_file_location('upstream_discovery', ROOT)
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


class UpstreamDiscoveryTests(unittest.TestCase):
    def test_exact_match_not_latest(self):
        report = {'distro_name': 'make', 'host_package_candidate': 'make',
                  'host_version_observed': '4.4.1-3'}
        result = discovery.resolve_package(report, lambda url: [
            'make-4.4.1.tar.gz', 'make-9.9.tar.xz'])
        self.assertEqual(result['status'], 'candidate-exact-match')
        self.assertEqual(result['upstream']['version'], '4.4.1')

    def test_arch_vcs_revision_unresolved(self):
        result = discovery.resolve_package({'distro_name': 'gcc',
            'host_version_observed': '16.2.1+r23+gd564253eb6c8-1'})
        self.assertEqual(result['status'], 'unresolved')
        self.assertEqual(result['reason'], 'host-version-needs-package-specific-mapping')

    def test_no_silent_patchlevel_fallback(self):
        result = discovery.resolve_package({'distro_name': 'bash',
            'host_version_observed': '5.3.20-1'}, lambda _: ['bash-5.3.tar.gz'])
        self.assertEqual(result['reason'], 'no-exact-upstream-release')

    def test_epoch_and_missing(self):
        self.assertEqual(discovery.arch_pkgver('2:2.16-1'), '2.16')
        result = discovery.resolve_package({'distro_name':'tar','host_version_observed':None})
        self.assertEqual(result['reason'], 'host-counterpart-missing')

    def test_scope_is_audit(self):
        report={'schema_version':1,'host_kind':'arch','manifest_sha256':'abc',
                'packages':[{'distro_name':'make','host_version_observed':'4.4.1-3'}]}
        result=discovery.discover_from_audit(report,lambda _:['make-4.4.1.tar.gz'])
        self.assertEqual(len(result['packages']),1)
        self.assertEqual(result['summary']['matched'],1)


if __name__=='__main__':
    unittest.main()
