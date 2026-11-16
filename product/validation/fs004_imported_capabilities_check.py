#!/usr/bin/env python3
"""Targeted FS-004 Stage 1B provenance contract; no regression suite."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'product/src'))
from build.selection import SelectionError
from build.native_imported_capabilities import (_pinned_stage1b,
    authenticate_stage1b_provider, VerifiedStage1BProvider, STAGE1B)
from build.bootstrap.cross_chroot_handoff import ARCHIVE_NAME, METADATA_NAME
pins = _pinned_stage1b(STAGE1B)
assert set(('gcc','make','bash','binutils')).issubset(pins)
with TemporaryDirectory() as d:
    base=Path(d).resolve()
    archive=base/ARCHIVE_NAME; archive.write_bytes(b'fixture only')
    root=base/'root'; (root/'usr/bin').mkdir(parents=True)
    for exe in ('gcc','g++','make','bash','as','ld'):
        path=root/'usr/bin'/exe
        path.write_bytes(b'fixture executable')
        path.chmod(0o755)
    selected=[{'package':name,'version':version,'sha256':checksum}
              for name,(version,checksum) in pins.items()]
    metadata={'artifact':{'sha256':'f'*64},'sources':selected}
    (base/METADATA_NAME).write_text(json.dumps(metadata))
    with patch('build.native_imported_capabilities.validate_cross_chroot_handoff') as validator:
        provider=authenticate_stage1b_provider(archive,root)
        validator.assert_called_once()
        assert isinstance(provider,VerifiedStage1BProvider)
        assert dict(provider.capabilities)['gcc']==pins['gcc'][0]
        assert provider.archive_sha256=='f'*64
        (root/'usr/bin/gcc').unlink()
        try:authenticate_stage1b_provider(archive,root)
        except SelectionError:pass
        else:raise AssertionError('missing restored native compiler accepted')
        (root/'usr/bin/gcc').symlink_to('/usr/bin/gcc')
        try:authenticate_stage1b_provider(archive,root)
        except SelectionError:pass
        else:raise AssertionError('host-absolute compiler symlink accepted')
        (root/'usr/bin/gcc').unlink()
        (root/'usr/bin/gcc').write_bytes(b'fixture executable')
        (root/'usr/bin/gcc').chmod(0o755)
        changed=dict(metadata)
        changed['sources']=[dict(item) for item in selected]
        for item in changed['sources']:
            if item['package']=='gcc':item['version']='0.0'
        (base/METADATA_NAME).write_text(json.dumps(changed))
        try:authenticate_stage1b_provider(archive,root)
        except SelectionError:pass
        else:raise AssertionError('incorrect handoff GCC identity accepted')
print('PASS FS-004 targeted Stage 1B capability authentication')
