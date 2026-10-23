"""Reject host compiler inputs and mismatched exported files."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bootstrap'))
from cross_toolchain import ToolchainError, require_target_paths, archive_root
from project_build import verify_archive

class AcceptanceTests(unittest.TestCase):
    def test_target_includes(self):
        paths = require_target_paths('#include <...> search starts here:\n /toolchain/usr/include\nEnd of search list.\n', kind='includes')
        self.assertEqual(paths, ['/toolchain/usr/include'])

    def test_host_include_rejected(self):
        with self.assertRaisesRegex(ToolchainError, 'host or unsafe'):
            require_target_paths('#include <...> search starts here:\n /usr/include\nEnd of search list.\n', kind='includes')

    def test_host_startup_rejected(self):
        with self.assertRaises(ToolchainError):
            require_target_paths('/usr/lib/crt1.o\n', kind='startup')

    def test_archive_hard_link_matches_installed_root(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            root = folder / 'root'
            root.mkdir()
            (root / 'gcc').write_bytes(b'compiler')
            os.link(root / 'gcc', root / 'g++')
            archive = folder / 'root.tar.xz'
            archive_root(root, archive)
            verify_archive(root, archive)

    def test_archive_hard_link_replacement_rejected(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            root = folder / 'root'
            root.mkdir()
            (root / 'gcc').write_bytes(b'compiler')
            os.link(root / 'gcc', root / 'g++')
            archive = folder / 'root.tar.xz'
            archive_root(root, archive)
            (root / 'g++').unlink()
            (root / 'g++').write_bytes(b'compiler')
            with self.assertRaisesRegex(ToolchainError, 'hard link differs'):
                verify_archive(root, archive)

    def test_archive_member_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            root=folder/'root'; root.mkdir()
            (root/'file').write_text('original')
            archive=folder/'root.tar.xz'
            archive_root(root,archive)
            verify_archive(root,archive)
            (root/'file').write_text('changed')
            with self.assertRaises(ToolchainError):
                verify_archive(root,archive)

if __name__ == '__main__':
    unittest.main()
