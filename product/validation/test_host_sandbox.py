"""Host-sandbox isolation and command construction regression tests."""
from __future__ import annotations
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from build.host_sandbox import SandboxError, probe_bubblewrap, recipe_command, run_recipe


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.work = self.base / 'build'
        self.root = self.base / 'root'
        self.work.mkdir(); self.root.mkdir()
        (self.work/'gcc/source').mkdir(parents=True)
        (self.work/'gcc/build').mkdir(parents=True)
        self.recipe = self.base/'recipe.sh'
        self.recipe.write_text('set -eu\ntest "$DISTRO_SOURCE_DIR" = /work/gcc/source\n')
        self.kwargs = dict(source_dir='/work/gcc/source', build_dir='/work/gcc/build',
                           package='gcc',version='16.2.0',step_id='gcc-pass1')

    @patch('build.host_sandbox.shutil.which', return_value='/usr/bin/bwrap')
    def test_command_mounts(self, _):
        cmd=recipe_command(self.work,self.root,self.recipe,**self.kwargs)
        for item in ('--unshare-user','--unshare-net','--clearenv','--proc','--tmpfs','--dir','/toolchain','/work'):
            self.assertIn(item,cmd)
        self.assertNotIn('LD_LIBRARY_PATH',cmd)
        self.assertEqual(cmd[-2:], ['/bin/bash','/recipe/selected.sh'])

    @patch('build.host_sandbox.shutil.which', return_value=None)
    def test_missing_bwrap(self, _):
        with self.assertRaises(SandboxError):
            run_recipe(self.work,self.root,self.recipe,**self.kwargs)

    @patch('build.host_sandbox.shutil.which', return_value='/usr/bin/bwrap')
    def test_bad_source(self, _):
        with self.assertRaises(SandboxError):
            recipe_command(self.work,self.root,self.recipe,**{**self.kwargs,'source_dir':'/etc'})

    @patch('build.host_sandbox.shutil.which', return_value='/usr/bin/bwrap')
    def test_mount_overlap_and_symlinks(self, _):
        with self.assertRaises(SandboxError):
            recipe_command(self.work,self.work,self.recipe,**self.kwargs)
        link=self.base/'linked'; link.symlink_to(self.work,target_is_directory=True)
        with self.assertRaises(SandboxError):
            recipe_command(link,self.root,self.recipe,**self.kwargs)

    @patch('build.host_sandbox.shutil.which', return_value='/usr/bin/bwrap')
    def test_probe_command_rejects_write_and_host_env_leak(self, _):
        with patch('build.host_sandbox.Path.is_file', return_value=True),              patch('build.host_sandbox.subprocess.run') as run:
            probe_bubblewrap()
            cmd = run.call_args.args[0]
            self.assertIn('DISTRO_PREFLIGHT_SECRET', cmd[-1])
            self.assertIn('/etc/distro-preflight-write-test', cmd[-1])
            self.assertEqual(run.call_args.kwargs['env']['DISTRO_PREFLIGHT_SECRET'], 'not-for-sandbox')
            self.assertIn('--clearenv', cmd)

    def test_actual_bwrap_probe_and_recipe(self):
        if not shutil.which('bwrap'):
            self.skipTest('Bubblewrap not installed on test host; real sandbox must pass on qualified Build host')
        probe_bubblewrap()
        run_recipe(self.work,self.root,self.recipe,**self.kwargs)

if __name__=='__main__':
    unittest.main()
