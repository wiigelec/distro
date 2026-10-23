"""Execution-time host and source qualification without host package mutation."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from source_artifacts import SourceError, expected_checksum, https_url, read_https, source_spec


class HostCheckError(ValueError):
    """An execution prerequisite was not demonstrated."""


def checked_run(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HostCheckError(f'{args[0]} execution unavailable: {exc}') from exc
    if result.returncode:
        raise HostCheckError(f'{args[0]} failed ({result.returncode}): {result.stderr[-350:]}')
    return result


def qualify_execution_host() -> dict:
    """Demonstrate native compilers and read-only-host Bubblewrap execution."""
    if os.geteuid() == 0:
        raise HostCheckError('bootstrap host qualification must run unprivileged')
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise HostCheckError('initial toolchain requires Linux x86_64 host')
    commands = ('cc', 'c++', 'make', 'as', 'ld', 'ar', 'ranlib', 'tar', 'readelf',
                'bwrap', 'python3')
    found = {name: shutil.which(name) for name in commands}
    missing = [name for name, path in found.items() if not path]
    if missing:
        raise HostCheckError('missing required host commands: ' + ', '.join(missing))
    environment = ('CC', 'CXX', 'LD', 'AR', 'AS', 'LIBRARY_PATH', 'LD_LIBRARY_PATH',
                   'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'CONFIG_SITE',
                   'PKG_CONFIG_PATH', 'PKG_CONFIG_LIBDIR')
    contaminated = [name for name in environment if os.environ.get(name)]
    if contaminated:
        raise HostCheckError('build environment requires review/unsetting: ' + ', '.join(contaminated))
    with tempfile.TemporaryDirectory(prefix='distro-host-check-') as folder:
        root = Path(folder)
        for suffix, compiler in (('c', 'cc'), ('cc', 'c++')):
            source = root / ('probe.' + suffix)
            executable = root / ('probe-' + suffix)
            source.write_text('int main(void) { return 0; }\n', encoding='utf-8')
            checked_run([found[compiler], str(source), '-o', str(executable)], timeout=60)
            checked_run([str(executable)])
        sandbox = [found['bwrap'], '--die-with-parent', '--new-session', '--unshare-user',
                   '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts',
                   '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
                   '--bind', str(root), '/work', '--chdir', '/work', '--clearenv',
                   '--setenv', 'PATH', '/usr/bin:/bin']
        for name in ('usr', 'bin', 'sbin', 'lib', 'lib64', 'etc'):
            host = Path('/') / name
            if host.exists():
                sandbox.extend(['--ro-bind', str(host), str(host)])
        checked_run(sandbox + ['--', '/usr/bin/sh', '-c',
                    'test -w /work && ! touch /usr/.distro-host-check && touch /work/writable'], timeout=30)
        if not (root / 'writable').is_file():
            raise HostCheckError('Bubblewrap writable workspace probe failed')
    return {'architecture': platform.machine(), 'kernel': platform.release(),
            'commands': {name: {'path': found[name],
                                  'version': checked_run([found[name], '--version']).stdout.splitlines()[:1]}
                         for name in ('cc', 'c++', 'make', 'as', 'ld', 'bwrap')},
            'c_compiler': 'passed', 'cxx_compiler': 'passed', 'bubblewrap': 'passed'}


def assert_resource_available(url: str) -> None:
    """Check selected HTTPS resource presence without downloading its archive."""
    https_url(url)
    request = Request(url, method='HEAD', headers={'User-Agent': 'Distro-preflight/1'})
    try:
        with urlopen(request, timeout=30) as response:
            https_url(response.geturl())
            if response.status >= 400:
                raise HostCheckError(f'upstream resource unavailable: {url}')
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise HostCheckError(f'upstream resource unavailable: {url}: {exc}') from exc


def qualify_source_availability(packages: list[dict]) -> dict:
    checked = []
    for item in packages:
        name = item['distro_name']
        try:
            spec = source_spec(item['upstream'])
            assert_resource_available(spec['url'])
            if spec['verification_method'] == 'detached-openpgp':
                if not (shutil.which('gpg') or shutil.which('gpgv')):
                    raise HostCheckError('OpenPGP verification executable unavailable')
                assert_resource_available(spec['signature_url'])
            else:
                checksum = read_https(spec['checksum_url'], limit=2_000_000)
                expected_checksum(checksum, spec['filename'], spec['checksum_algorithm'])
        except (SourceError, HostCheckError, ValueError, OSError) as exc:
            raise HostCheckError(f'{name}: {exc}') from exc
        checked.append(name)
    return {'available': checked, 'count': len(checked)}
