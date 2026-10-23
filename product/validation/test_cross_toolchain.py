"""Safety and contract tests for cross-toolchain construction."""
import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bootstrap'))
from cross_toolchain import (ToolchainError, validate_recipe, checked_source_extract,
                             sandbox_command, archive_root, STAGES, ROOT)
import json


class ToolchainTests(unittest.TestCase):
    def test_all_recipe_structures(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                validate_recipe(json.loads((ROOT / 'recipes' / (stage + '.json')).read_text()), stage)

    def test_shell_not_an_execution_interface(self):
        for stage in STAGES:
            recipe = json.loads((ROOT / 'recipes' / (stage + '.json')).read_text())
            for step in recipe['steps']:
                self.assertNotIn(step['argv'][0], ('sh', 'bash', '/bin/sh', '/bin/bash'))

    def test_invalid_recipe_rejected(self):
        with self.assertRaises(ToolchainError):
            validate_recipe({'schema_version': 1, 'name': 'gcc', 'source_package':'gcc',
                             'steps': [{'name':'x','argv':['make']}],
                             'required_outputs':['/toolchain/x']}, 'gcc')

    def test_sandbox_host_ro_and_workspace_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, r = Path(tmp) / 'work', Path(tmp) / 'root'
            w.mkdir(); r.mkdir()
            with patch('cross_toolchain.os.geteuid', return_value=1000), \
                 patch('cross_toolchain.shutil.which', return_value='/usr/bin/bwrap'):
                command = sandbox_command(w,r,['make'])
            self.assertIn('--unshare-net', command)
            self.assertIn('--clearenv', command)
            self.assertIn('--bind', command)
            self.assertIn('--ro-bind', command)
            self.assertEqual(command[-2:], ['--','make'])

    def test_no_root_host_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, r = Path(tmp) / 'work', Path(tmp) / 'root'
            w.mkdir(); r.mkdir()
            with patch('cross_toolchain.os.geteuid', return_value=0):
                with self.assertRaises(ToolchainError):
                    sandbox_command(w,r,['make'])

    def test_tar_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'archive.tar'
            with tarfile.open(archive, 'w') as stream:
                info = tarfile.TarInfo('../escape')
                content=b'x';info.size=len(content)
                stream.addfile(info, io.BytesIO(content))
            with self.assertRaises(ToolchainError):
                checked_source_extract(archive, Path(tmp) / 'extracted')

    def test_tar_single_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'archive.tar'
            with tarfile.open(archive, 'w') as stream:
                for name in ('a/x','b/y'):
                    info=tarfile.TarInfo(name);info.size=1
                    stream.addfile(info,io.BytesIO(b'x'))
            with self.assertRaises(ToolchainError):
                checked_source_extract(archive, Path(tmp)/'out')

    def test_export_archive_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir();(root/'file').write_text('content')
            report=archive_root(root,Path(tmp)/'root.tar.xz')
            self.assertEqual(len(report['sha256']),64)
            self.assertEqual(report['entries'],[{'path':'file','type':'file'}])

if __name__ == '__main__':
    unittest.main()
