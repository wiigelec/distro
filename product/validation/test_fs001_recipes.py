"""Development-only structural checks for directly executed FS-001 Bash recipes."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / 'src' / 'build' / 'bootstrap' / 'cross-toolchain' / 'recipes'
NAMES = ('binutils-pass1.sh', 'gcc-pass1.sh', 'linux-headers.sh', 'glibc.sh', 'gcc-libstdcpp.sh')

class RecipeTests(unittest.TestCase):
    def test_all_recipe_files_exist_and_use_strict_bash(self):
        for name in NAMES:
            with self.subTest(recipe=name):
                data = (RECIPES / name).read_text()
                self.assertTrue(data.startswith('#!/usr/bin/env bash\nset -euo pipefail\n'))
                self.assertIn('DISTRO_SOURCE_DIR', data)
                self.assertIn('DISTRO_ROOT_DIR', data)
                self.assertNotIn('curl ', data)
                self.assertNotIn('wget ', data)
                self.assertNotIn('http://', data)
                self.assertNotIn('https://', data)
    def test_bash_syntax(self):
        bash = shutil.which('bash')
        if bash is None:
            self.skipTest('Bash unavailable')
        for name in NAMES:
            with self.subTest(recipe=name):
                cp = subprocess.run([bash, '-n', str(RECIPES/name)], capture_output=True, text=True)
                self.assertEqual(cp.returncode, 0, cp.stderr)
    def test_gcc_supplement_contract(self):
        self.assertIn('for lib in gmp mpfr mpc', (RECIPES/'gcc-pass1.sh').read_text())
    def test_glibc_does_not_fetch_patches(self):
        data = (RECIPES/'glibc.sh').read_text()
        self.assertNotIn('patch -p', data)
        self.assertIn('DESTDIR="$DISTRO_ROOT_DIR"', data)

if __name__ == '__main__':
    unittest.main()
