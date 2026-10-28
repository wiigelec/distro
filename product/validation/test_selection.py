import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import hashlib
import io
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from build.selection import load_manifests, select_steps, SelectionError, Source
from build.sources import fetch_verified, extract_verified

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.m = self.root/'packages'; self.r = self.root/'recipes'
        self.m.mkdir(); self.r.mkdir()
        (self.m/'gcc.yaml').write_text('name: gcc\nsource:\n  url: https://example.org/gcc-{version}.tar.xz\n  sha256: '+ 'a'*64+'\ndependencies: []\nhost_tools: [make]\n')
        (self.r/'pass1.sh').write_text('true\n')
        self.lst=self.root/'list.yaml'
        self.lst.write_text('steps:\n  - {id: gcc-pass1, name: gcc, version: "16.2.0", recipe: pass1.sh}\n')
    def test_select(self):
        steps=select_steps(self.lst, load_manifests(self.m), self.r)
        self.assertEqual((steps[0].name,steps[0].version),('gcc','16.2.0'))
    def test_reject_unquoted_numeric_version(self):
        self.lst.write_text('steps:\n  - {name: gcc, version: 16.2, recipe: pass1.sh}\n')
        with self.assertRaises(SelectionError):select_steps(self.lst,load_manifests(self.m),self.r)
    def test_reject_unsafe_recipe(self):
        self.lst.write_text('steps:\n  - {name: gcc, version: "16.2.0", recipe: ../other.sh}\n')
        with self.assertRaises(SelectionError):select_steps(self.lst,load_manifests(self.m),self.r)
    def test_reject_missing_dependency(self):
        (self.m/'gcc.yaml').write_text((self.m/'gcc.yaml').read_text().replace('dependencies: []','dependencies: [binutils]'))
        with self.assertRaises(SelectionError):select_steps(self.lst,load_manifests(self.m),self.r)
    def test_digest_rejection_preserves_existing(self):
        dest=self.root/'archive'; dest.write_bytes(b'prior')
        class Response(io.BytesIO):
            def geturl(self):return 'https://example.org/archive'
        with patch('build.sources.urlopen',return_value=Response(b'wrong')):
            with self.assertRaises(SelectionError):fetch_verified(Source('https://example.org/archive','a'*64),'1',dest)
        self.assertEqual(dest.read_bytes(),b'prior')
    def test_archive_traversal_rejected(self):
        archive=self.root/'bad.tar'; dest=self.root/'out'
        with tarfile.open(archive,'w') as tar:
            content=b'bad'; ti=tarfile.TarInfo('../escaped');ti.size=len(content);tar.addfile(ti,io.BytesIO(content))
        with self.assertRaises(SelectionError):extract_verified(archive,dest)
        self.assertFalse((self.root/'escaped').exists())

    def test_repeated_gcc_steps(self):
        (self.r/'pass2.sh').write_text('true\n')
        self.lst.write_text('steps:\n  - {id: gcc-pass1, name: gcc, version: "16.2.0", recipe: pass1.sh}\n  - {id: gcc-libstdcpp, name: gcc, version: "16.2.0", recipe: pass2.sh}\n')
        steps = select_steps(self.lst, load_manifests(self.m), self.r)
        self.assertEqual([s.id for s in steps], ['gcc-pass1', 'gcc-libstdcpp'])

    def test_cyclic_manifest_dependencies_rejected(self):
        (self.m/'gcc.yaml').write_text((self.m/'gcc.yaml').read_text().replace('dependencies: []','dependencies: [binutils]'))
        (self.m/'binutils.yaml').write_text('name: binutils\nsource:\n  url: https://example.org/binutils-{version}.tar.xz\n  sha256: '+ 'b'*64+'\ndependencies: [gcc]\n')
        (self.r/'binutils.sh').write_text('true\n')
        self.lst.write_text('steps:\n  - {name: binutils, version: "2.47", recipe: binutils.sh}\n  - {name: gcc, version: "16.2.0", recipe: pass1.sh}\n')
        with self.assertRaises(SelectionError):
            select_steps(self.lst, load_manifests(self.m), self.r)

    def test_redirect_to_http_rejected(self):
        class Response(io.BytesIO):
            def geturl(self): return 'http://example.org/archive'
        with patch('build.sources.urlopen', return_value=Response(b'data')):
            with self.assertRaises(SelectionError):
                fetch_verified(Source('https://example.org/archive', hashlib.sha256(b'data').hexdigest()), '1', self.root/'archive')
        self.assertFalse((self.root/'archive').exists())

    def test_safe_symlink_extraction(self):
        archive=self.root/'links.tar'; dest=self.root/'linked'
        with tarfile.open(archive,'w') as tar:
            content=b'hello'; entry=tarfile.TarInfo('tree/target'); entry.size=len(content)
            tar.addfile(entry,io.BytesIO(content))
            link=tarfile.TarInfo('tree/alias');link.type=tarfile.SYMTYPE;link.linkname='target';tar.addfile(link)
        extract_verified(archive,dest)
        self.assertEqual((dest/'tree/alias').read_bytes(),b'hello')
        self.assertTrue((dest/'tree/alias').is_symlink())

    def test_symlink_escape_rejected(self):
        archive=self.root/'escape.tar';dest=self.root/'unsafe'
        with tarfile.open(archive,'w') as tar:
            link=tarfile.TarInfo('dir/escape');link.type=tarfile.SYMTYPE;link.linkname='../../outside';tar.addfile(link)
        with self.assertRaises(SelectionError):extract_verified(archive,dest)
        self.assertFalse(dest.exists())

    def test_special_device_rejected(self):
        archive=self.root/'device.tar'; dest=self.root/'out-device'
        with tarfile.open(archive,'w') as tar:
            device=tarfile.TarInfo('dev');device.type=tarfile.CHRTYPE;tar.addfile(device)
        with self.assertRaises(SelectionError):extract_verified(archive,dest)
        self.assertFalse(dest.exists())

if __name__=='__main__':unittest.main()
