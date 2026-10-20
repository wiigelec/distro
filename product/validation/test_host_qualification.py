import importlib.util
import pathlib
import unittest

FILE = pathlib.Path(__file__).resolve().parents[1] / 'src/bootstrap/host_qualification.py'
spec = importlib.util.spec_from_file_location('host_qualification', FILE)
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


def manifest():
    return {'schema_version': 1, 'closure_complete': True, 'packages': [
        {'distro_name': 'gcc', 'host_package': 'gcc', 'upstream': {
            'name': 'gcc', 'version': '15.1.0', 'official_url': 'https://gcc.gnu.org/',
            'mapping_basis': 'reviewed Arch version correspondence'}}]}


class QualificationTests(unittest.TestCase):
    def test_arch_version_epoch_and_release(self):
        self.assertEqual(qualification.parse_arch_version('1:15.1.0-2')['pkgver'], '15.1.0')
    def test_valid_explicit_mapping(self):
        self.assertEqual(qualification.qualify(manifest(), {'gcc': '15.1.0-2'})['status'], 'qualified-mapping-baseline')
    def test_missing_package_blocks(self):
        with self.assertRaises(qualification.QualificationError):
            qualification.qualify(manifest(), {})
    def test_incomplete_manifest_blocks(self):
        doc = manifest(); doc['closure_complete'] = False
        with self.assertRaises(qualification.QualificationError):
            qualification.qualify(doc, {'gcc': '15.1.0-2'})
    def test_ambiguous_mapping_blocks(self):
        doc = manifest(); del doc['packages'][0]['upstream']['mapping_basis']
        with self.assertRaises(qualification.QualificationError):
            qualification.qualify(doc, {'gcc': '15.1.0-2'})
    def test_source_must_be_https(self):
        doc = manifest(); doc['packages'][0]['upstream']['official_url'] = 'http://example.com'
        with self.assertRaises(qualification.QualificationError):
            qualification.qualify(doc, {'gcc': '15.1.0-2'})


if __name__ == '__main__':
    unittest.main()
