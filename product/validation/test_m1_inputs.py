"""Cross-toolchain input readiness is derived from actual audited candidates."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1] / 'src' / 'bootstrap' / 'm1_inputs.py'
spec = importlib.util.spec_from_file_location('m1_inputs', HERE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class M1InputsTests(unittest.TestCase):
    def test_reports_absent_glibc_and_api_headers(self):
        audit = {'packages': [
            {'distro_name': 'binutils', 'upstream_discovery': {
                'status': 'candidate-exact-match', 'upstream': {'version':'2.47','artifact_url':'https://example.org/binutils.tar.xz'}}},
            {'distro_name': 'gcc', 'upstream_discovery': {
                'status': 'candidate-exact-match', 'upstream': {'version':'16','artifact_url':'https://example.org/gcc.tar.xz'}}}] }
        result = module.evaluate_inputs(audit)
        self.assertEqual(result['status'], 'discovery-incomplete')
        self.assertEqual(result['missing_or_unresolved'], ['linux-api-headers', 'glibc'])

    def test_discovery_does_not_claim_qualification(self):
        audit={'packages':[{'distro_name':name, 'upstream_discovery': {
            'status':'candidate-exact-match','upstream': {'version':'1','artifact_url':'https://example.org/src.tar.xz'}}}
            for name in module.SOURCE_OWNERS]}
        result=module.evaluate_inputs(audit)
        self.assertEqual(result['status'], 'discovered-not-qualified')
        self.assertEqual(result['missing_or_unresolved'], [])

    def test_reject_duplicate_records(self):
        with self.assertRaises(ValueError):
            module.evaluate_inputs({'packages':[{'distro_name':'gcc'},{'distro_name':'gcc'}]})


if __name__=='__main__':
    unittest.main()
