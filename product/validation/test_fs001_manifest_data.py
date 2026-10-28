"""Check pinned source identities without implying recipes or builds exist."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from build.selection import load_manifests, _yaml, _keys, _name, _version

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / 'src' / 'build' / 'packages'
LIST = ROOT / 'src' / 'build' / 'lists' / 'cross-toolchain.yaml'

class PinnedManifestTests(unittest.TestCase):
    def test_package_set_and_checksums(self):
        ms = load_manifests(PACKAGES)
        self.assertEqual(set(ms), {'binutils','gcc','linux','glibc'})
        self.assertEqual(set(ms['gcc'].supplements), {'gmp','mpfr','mpc'})
        for m in ms.values():
            self.assertEqual(len(m.source.sha256), 64)
            self.assertTrue(all(c in '0123456789abcdef' for c in m.source.sha256))
            for source in m.supplements.values():
                self.assertEqual(len(source.sha256), 64)

    def test_exact_order_and_repeated_gcc(self):
        d = _yaml(LIST)
        _keys(d, {'steps'})
        steps = d['steps']
        expected = [
            ('binutils-pass1','binutils','2.47','recipes/binutils-pass1.sh'),
            ('gcc-pass1','gcc','16.2.0','recipes/gcc-pass1.sh'),
            ('linux-headers','linux','7.1.8','recipes/linux-headers.sh'),
            ('glibc','glibc','2.44','recipes/glibc.sh'),
            ('gcc-libstdcpp','gcc','16.2.0','recipes/gcc-libstdcpp.sh'),
        ]
        self.assertIsInstance(steps, list)
        actual=[]
        for step in steps:
            _keys(step, {'id','name','version','recipe'})
            self.assertTrue(_name(step['id']) and _name(step['name']))
            self.assertTrue(_version(step['version']))
            self.assertIsInstance(step['recipe'],str)
            actual.append(tuple(step[k] for k in ('id','name','version','recipe')))
        self.assertEqual(actual, expected)

if __name__ == '__main__': unittest.main()
