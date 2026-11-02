"""Focused FS-002 Stage 1A import integrity checks (stdlib unittest)."""
from __future__ import annotations

import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from build.bootstrap.cross_chroot_import import CrossChrootImportError, restore_cross_toolchain
from build.bootstrap.cross_toolchain import TARGET
from build.bootstrap.cross_toolchain_metadata import ARCHIVE_NAME, METADATA_NAME


class HandoffImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.input = self.path / 'input'
        self.input.mkdir()
        self.root = self.path / 'root'
        self.root.mkdir()
        self.archive = self.input / ARCHIVE_NAME
        with tarfile.open(self.archive, 'w:xz', format=tarfile.PAX_FORMAT) as tar:
            directory = tarfile.TarInfo('./usr')
            directory.type = tarfile.DIRTYPE
            tar.addfile(directory)
            data = b'placeholder for safely archived target file\n'
            entry = tarfile.TarInfo('./usr/file')
            entry.size = len(data)
            tar.addfile(entry, io.BytesIO(data))
        from build.bootstrap.cross_toolchain_metadata import sha256_file
        self.metadata = {
            'schema_version': 1,
            'artifact': {'type': 'cross-toolchain', 'stage': '1A', 'filename': ARCHIVE_NAME,
                         'format': 'tar.xz', 'sha256': sha256_file(self.archive),
                         'size_bytes': self.archive.stat().st_size},
            'toolchain': {'target': TARGET, 'sysroot': '/toolchain', 'tools_prefix': '/toolchain/tools'},
            'sources': [{'step': 'binutils-pass1', 'package': 'binutils', 'version': '2.47',
                         'sha256': 'a' * 64, 'recipe': 'binutils.sh', 'supplements': []}],
            'verification': {'functional': 'passed', 'relocation': 'passed'},
        }
        self.write_metadata()

    def write_metadata(self):
        (self.input / METADATA_NAME).write_text(json.dumps(self.metadata))

    def test_import_validated_pair(self):
        result = restore_cross_toolchain(self.archive, self.root)
        self.assertEqual(result['toolchain']['target'], TARGET)
        self.assertEqual((self.root / 'usr/file').read_bytes(),
                         b'placeholder for safely archived target file\n')

    def test_archive_bytes_mismatch_fails(self):
        self.metadata['artifact']['sha256'] = '0' * 64
        self.write_metadata()
        with self.assertRaises(CrossChrootImportError):
            restore_cross_toolchain(self.archive, self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_wrong_target_fails(self):
        self.metadata['toolchain']['target'] = 'aarch64-unknown-linux-gnu'
        self.write_metadata()
        with self.assertRaises(CrossChrootImportError):
            restore_cross_toolchain(self.archive, self.root)

    def test_missing_metadata_fails(self):
        (self.input / METADATA_NAME).unlink()
        with self.assertRaises(CrossChrootImportError):
            restore_cross_toolchain(self.archive, self.root)

    def test_nonempty_destination_fails(self):
        (self.root / 'existing').touch()
        with self.assertRaises(CrossChrootImportError):
            restore_cross_toolchain(self.archive, self.root)

    def test_escaping_archive_member_fails(self):
        with tarfile.open(self.archive, 'w:xz') as tar:
            item = tarfile.TarInfo('../outside')
            item.size = 1
            tar.addfile(item, io.BytesIO(b'x'))
        from build.bootstrap.cross_toolchain_metadata import sha256_file
        self.metadata['artifact']['sha256'] = sha256_file(self.archive)
        self.metadata['artifact']['size_bytes'] = self.archive.stat().st_size
        self.write_metadata()
        with self.assertRaises(CrossChrootImportError):
            restore_cross_toolchain(self.archive, self.root)
        self.assertFalse((self.path / 'outside').exists())


if __name__ == '__main__':
    unittest.main()
