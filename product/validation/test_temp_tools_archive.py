"""Archive-member validation for verified cross-toolchain handoffs."""
import importlib.util
import io
from pathlib import Path
import tarfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'src/bootstrap/temporary_tools/temp_tools_bootstrap.py'
spec = importlib.util.spec_from_file_location('temp_tools_bootstrap_archive_test', SOURCE)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def archive_with_link(target, *, symlink=False):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        data = b'compiler payload'
        entry = tarfile.TarInfo('usr/bin/compiler')
        entry.size = len(data)
        archive.addfile(entry, io.BytesIO(data))
        other = tarfile.TarInfo('usr/bin/compiler++')
        other.type = tarfile.SYMTYPE if symlink else tarfile.LNKTYPE
        other.linkname = target
        archive.addfile(other)
    buffer.seek(0)
    return buffer


class ArchiveMemberTests(unittest.TestCase):
    def test_hard_link_to_prior_regular_file_is_accepted(self):
        with tarfile.open(fileobj=archive_with_link('usr/bin/compiler'), mode='r') as archive:
            members = bootstrap.archive_members(archive)
        self.assertEqual(len(members), 2)
        self.assertTrue(members[1].islnk())

    def test_hard_link_to_missing_file_is_rejected(self):
        with tarfile.open(fileobj=archive_with_link('usr/bin/missing'), mode='r') as archive:
            with self.assertRaisesRegex(RuntimeError, 'unsafe archive hard link'):
                bootstrap.archive_members(archive)

    def test_hard_link_path_traversal_is_rejected(self):
        with tarfile.open(fileobj=archive_with_link('../../etc/passwd'), mode='r') as archive:
            with self.assertRaisesRegex(RuntimeError, 'unsafe archive hard link'):
                bootstrap.archive_members(archive)

    def test_symlink_cannot_be_a_hard_link_target(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            first = tarfile.TarInfo('usr/bin/link')
            first.type = tarfile.SYMTYPE
            first.linkname = 'compiler'
            archive.addfile(first)
            second = tarfile.TarInfo('usr/bin/alias')
            second.type = tarfile.LNKTYPE
            second.linkname = 'usr/bin/link'
            archive.addfile(second)
        buffer.seek(0)
        with tarfile.open(fileobj=buffer, mode='r') as archive:
            with self.assertRaisesRegex(RuntimeError, 'unsafe archive hard link'):
                bootstrap.archive_members(archive)


if __name__ == '__main__':
    unittest.main()
