"""Manage candidate-only dependency closure and fresh-root installation.

An installed candidate is NOT an accepted distro-buildroot collection. Only a
future independent closure gate can promote a completed collection selection.
No host package installer or tar extraction into an existing root is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile

from manage.package import PackageError, _json_bytes, _regular_directory, verify
from manage.repository import ARTIFACTS, _sync_dir, verify_repository
from manage.layout import LINKS, canonical_path, canonical_claims

STATE_DIR = '.distro'
STATE_NAME = 'installed.json'


def _identity_key(record: dict) -> tuple:
    identity = record['identity']
    return (identity['name'], identity['version'], identity['architecture'], identity['revision'])


def resolve_candidate(repo: Path, package: str = 'distro-buildroot') -> tuple[dict, ...]:
    """Resolve exact immutable records from a verified Manage repository.

    Ambiguous package versions/revisions, missing edges, and cycles fail closed.
    This resolution does not advertise an accepted collection selector.
    """
    index = verify_repository(repo)
    records = index['packages']
    by_name: dict[str, list[dict]] = {}
    for record in records:
        by_name.setdefault(record['identity']['name'], []).append(record)
    if package != 'distro-buildroot':
        raise PackageError('candidate installation requires distro-buildroot metapackage')
    if not by_name.get(package) or len(by_name[package]) != 1:
        raise PackageError('missing or ambiguous candidate metapackage')
    root_record = by_name[package][0]
    if root_record['paths'] or not root_record['relationships']:
        raise PackageError('invalid metadata-only collection root')
    visiting: set[str] = set()
    finished: set[str] = set()
    order: list[dict] = []
    target_arch = root_record['identity']['architecture']

    def visit(name: str, version: str) -> None:
        options = by_name.get(name, [])
        if len(options) != 1 or options[0]['identity']['version'] != version:
            raise PackageError(f'missing or ambiguous selected dependency: {name} {version}')
        record = options[0]
        if record['identity']['architecture'] != target_arch:
            raise PackageError(f'mixed architectures in candidate: {name}')
        if name in visiting:
            raise PackageError(f'candidate dependency cycle at {name}')
        if name in finished:
            return
        visiting.add(name)
        for relationship in record['relationships']:
            visit(relationship['name'], relationship['version'])
        visiting.remove(name)
        finished.add(name)
        order.append(record)

    visit(package, root_record['identity']['version'])
    if len([r for r in order if r['identity']['name'] != package]) != 13:
        raise PackageError('candidate does not select thirteen payload packages')
    expected_names = {'filesystem', 'bash', 'coreutils', 'sed', 'grep', 'gawk',
                      'make', 'diffutils', 'tar', 'binutils', 'gcc', 'linux', 'glibc'}
    if {r['identity']['name'] for r in order if r['identity']['name'] != package} != expected_names:
        raise PackageError('candidate package closure differs from FS-004 selection')
    # Filesystem owns the selected directory/link policy before any other
    # payload is materialized, regardless of otherwise valid topo tie-breaks.
    filesystem = next(r for r in order if r['identity']['name'] == 'filesystem')
    order = [filesystem] + [r for r in order if r is not filesystem]
    canonical_claims(order)  # Preflight all ownership before a private root exists.
    return tuple(order)


def _directory(root: Path, rel: str) -> Path:
    """Create or inspect a real directory without following any symlink ancestor."""
    node = root
    for part in rel.split('/'):
        node = node / part
        if node.is_symlink():
            raise PackageError(f'candidate path has symlink ancestor: {rel}')
        if node.exists():
            if not node.is_dir():
                raise PackageError(f'candidate path has non-directory ancestor: {rel}')
        else:
            node.mkdir(mode=0o700)
    return node


def _install_payload(archive: Path, records: list[dict], root: Path,
                     directory_modes: dict[str, int], leaf_owners: dict[str, tuple],
                     identity: tuple, *, filesystem: bool = False) -> None:
    """Apply verified members to a private root with no link traversal."""
    with tarfile.open(archive, 'r:xz') as package:
        members = {item.name: item for item in package.getmembers()[1:]}
        # Inventory path ownership is checked before writing each payload.
        for record in records:
            raw = record['path']
            # Only filesystem itself creates the literal selected alias links.
            # Other packages install through approved aliases into canonical
            # /usr paths, never by traversing a symlink on the host filesystem.
            rel = raw if filesystem and raw in LINKS else canonical_path(raw)
            kind = record['type']
            parts = rel.split('/')
            for n in range(1, len(parts)):
                _directory(root, '/'.join(parts[:n]))
            target = root / rel
            if kind == 'directory':
                current = directory_modes.setdefault(rel, record['mode'])
                if current != record['mode']:
                    raise PackageError(f'incompatible directory modes: {rel}')
                _directory(root, rel)
                continue
            if rel in leaf_owners or rel in directory_modes or target.exists() or target.is_symlink():
                raise PackageError(f'candidate leaf ownership conflict: {rel}')
            item = members['payload/' + raw]
            if kind == 'file':
                stream = package.extractfile(item)
                if stream is None:
                    raise PackageError(f'verified payload file absent: {rel}')
                fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                             getattr(os, 'O_NOFOLLOW', 0), 0o600)
                with os.fdopen(fd, 'wb') as output:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        output.write(block)
                    os.fchmod(output.fileno(), record['mode'])
                    output.flush()
                    os.fsync(output.fileno())
            elif kind == 'symlink':
                # verify() already checks relative targets remain inside root.
                os.symlink(record['target'], target)
            else:
                raise PackageError(f'unsupported candidate payload entry: {kind}')
            leaf_owners[rel] = identity


def _install_selected(repo: Path, destination: Path, records: tuple[dict, ...],
                      *, status: str, selection: str) -> Path:
    """Install a previously resolved, verified package selection privately.

    The destination must not exist. Nothing is exposed on partial failure; a
    persistent lock rejects concurrent installers and requires manual cleanup
    after interruption. This is intentionally NOT a completed-collection gate.
    """
    repo = _regular_directory(repo)
    destination = Path(destination).absolute()
    parent = _regular_directory(destination.parent)
    if destination.name in ('', '.', '..') or destination.exists() or destination.is_symlink():
        raise PackageError('candidate destination must not exist')
    if repo == parent or repo.is_relative_to(destination) or destination.is_relative_to(repo):
        raise PackageError('candidate root must be outside repository')
    canonical_claims(list(records))
    lock = parent / ('.' + destination.name + '.install.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                     getattr(os, 'O_NOFOLLOW', 0), 0o600)
    except FileExistsError as exc:
        raise PackageError('candidate installation lock exists') from exc
    published = False
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write('Manage candidate-only install\n')
            handle.flush()
            os.fsync(handle.fileno())
        # Private root shares a filesystem with the final destination.
        with tempfile.TemporaryDirectory(dir=parent, prefix='.candidate-root-') as private:
            root = Path(private) / 'root'
            root.mkdir(mode=0o700)
            modes: dict[str, int] = {}
            leaves: dict[str, tuple] = {}
            # Snapshot all intended canonical ownership before any writes.
            canonical_claims(list(records))
            for record in records:
                key = _identity_key(record)
                artifact = repo / ARTIFACTS / record['artifact']['filename']
                metadata = verify(artifact)
                if any(metadata[k] != record[k] for k in ('identity', 'relationships', 'paths')):
                    raise PackageError('candidate artifact diverged from repository record')
                _install_payload(artifact, record['paths'], root, modes, leaves, key,
                                 filesystem=record['identity']['name'] == 'filesystem')
            # Implicit ancestors of historical FS-003 packages default to 0755;
            # explicitly owned directories retain their selected exact modes.
            for walk_base, dirs, _files in os.walk(root, followlinks=False):
                for name in dirs:
                    path = Path(walk_base) / name
                    if path.is_symlink():
                        continue
                    rel = path.relative_to(root).as_posix()
                    if rel not in modes:
                        path.chmod(0o755)
            for rel in sorted(modes, key=lambda x: (-x.count('/'), x)):
                os.chmod(root / rel, modes[rel], follow_symlinks=False)
            root.chmod(0o755)
            state = {
                'schema_version': 1,
                'status': status,
                'selection': selection,
                'packages': [
                    {'identity': r['identity'], 'relationships': r['relationships'],
                     'artifact': r['artifact'], 'owned_paths': r['paths']}
                    for r in records],
            }
            if (root / STATE_DIR).exists() or (root / STATE_DIR).is_symlink():
                raise PackageError('reserved installed-state path occupied')
            state_dir = root / STATE_DIR
            state_dir.mkdir(mode=0o700)
            state_file = state_dir / STATE_NAME
            with state_file.open('xb') as output:
                output.write(_json_bytes(state))
                output.flush()
                os.fsync(output.fileno())
            _sync_dir(state_dir)
            _sync_dir(root)
            if destination.exists() or destination.is_symlink():
                raise PackageError('candidate destination became occupied')
            root.rename(destination)
            published = True
            _sync_dir(parent)
    except Exception as exc:
        if published:
            raise PackageError('candidate root promoted; inspect state before retry') from exc
        raise
    finally:
        try:
            lock.unlink(missing_ok=True)
            _sync_dir(parent)
        except OSError as exc:
            if published:
                raise PackageError('candidate promoted but install lock cleanup failed') from exc
            raise
    return destination


def resolve_prerequisites(repo: Path) -> tuple[dict, ...]:
    """Resolve only the selected FS-004 filesystem and Linux-headers prefix.

    An incomplete prefix is not a shell, compiler, or native construction root.
    It supplies independently packaged data for the bootstrap transition.
    """
    index = verify_repository(repo)
    records = index['packages']
    selected = {record['identity']['name']: record for record in records}
    if not {'filesystem', 'linux'}.issubset(selected):
        raise PackageError('prerequisite repository lacks filesystem or linux')
    if sum(r['identity']['name'] == 'filesystem' for r in records) != 1 or sum(
            r['identity']['name'] == 'linux' for r in records) != 1:
        raise PackageError('ambiguous selected prerequisite identities')
    if (selected['filesystem']['identity']['version'] != '1' or
            selected['linux']['identity']['version'] != '7.1.8'):
        raise PackageError('incorrect FS-004 prerequisite package versions')
    if any(record['identity']['architecture'] != 'x86_64' for record in records):
        raise PackageError('prerequisites must have x86_64 architecture')
    fs = selected['filesystem']
    linux = selected['linux']
    if fs['relationships'] or linux['relationships'] != [
            {'name': 'filesystem', 'version': '1'}]:
        raise PackageError('prerequisites must form the exact installed dependency closure')
    if not linux['paths'] or not all(
            (p['path'].startswith('usr/include/') or
             p['path'] in {'usr', 'usr/include'}) and
            p['type'] in {'file', 'directory', 'symlink'}
            for p in linux['paths']):
        raise PackageError('Linux prerequisite is not a headers-only payload')
    ordered = (fs, linux)
    canonical_claims(list(ordered))
    return ordered


def install_prerequisites(repo: Path, destination: Path) -> Path:
    """Install Manage-verified prerequisites without advertising full closure."""
    records = resolve_prerequisites(repo)
    return _install_selected(repo, destination, records,
                             status='prerequisites-not-accepted',
                             selection='filesystem+linux-headers')


def install_candidate(repo: Path, destination: Path) -> Path:
    """Install the complete unaccepted distro-buildroot candidate."""
    records = resolve_candidate(repo)
    return _install_selected(repo, destination, records,
                             status='candidate-not-accepted',
                             selection='distro-buildroot')


def resolve_toolchain_seed(repo: Path) -> tuple[dict, ...]:
    """Select exact independently published filesystem, Linux and Glibc artifacts.

    This three-package seed is *not* a runnable native toolchain or accepted
    distro-buildroot. No relationship may be invented from bootstrap provenance.
    """
    index = verify_repository(repo)
    records = index['packages']
    chosen = {}
    for record in records:
        name = record['identity']['name']
        if name in {'filesystem', 'linux', 'glibc'}:
            if name in chosen:
                raise PackageError(f'ambiguous toolchain seed package: {name}')
            chosen[name] = record
    if set(chosen) != {'filesystem', 'linux', 'glibc'}:
        raise PackageError('toolchain seed requires selected filesystem, linux, glibc')
    versions = {'filesystem': '1', 'linux': '7.1.8', 'glibc': '2.44'}
    for name, version in versions.items():
        identity = chosen[name]['identity']
        if identity['version'] != version or identity['architecture'] != 'x86_64':
            raise PackageError(f'wrong toolchain seed identity: {name}')
    if chosen['filesystem']['relationships']:
        raise PackageError('filesystem seed has installed dependencies')
    if chosen['linux']['relationships'] != [{'name': 'filesystem', 'version': '1'}]:
        raise PackageError('Linux seed relationship mismatch')
    if chosen['glibc']['relationships'] != [
            {'name': 'filesystem', 'version': '1'},
            {'name': 'linux', 'version': '7.1.8'}]:
        raise PackageError('Glibc seed relationship mismatch')
    # The complete selected repository may also contain subsequently built
    # artifacts. Resolve only the explicit, dependency-closed seed.
    records = (chosen['filesystem'], chosen['linux'], chosen['glibc'])
    canonical_claims(list(records))
    return records


def install_toolchain_seed(repo: Path, destination: Path) -> Path:
    """Install the unaccepted three-package seed through Manage alone."""
    return _install_selected(repo, destination, resolve_toolchain_seed(repo),
                             status='toolchain-seed-not-accepted',
                             selection='filesystem+linux+glibc')


def resolve_native_linker_seed(repo: Path) -> tuple[dict, ...]:
    """Resolve the exact unaccepted filesystem/Linux/Glibc/Binutils closure.

    Only published artifact records are authoritative. The installed Binutils
    dependency edges come from its selected FS-004 manifest; Stage 1B compiler
    provenance is never represented as a native installation relationship.
    This is data/dependency staging, not a complete executable buildroot.
    """
    index = verify_repository(repo)
    selected: dict[str, dict] = {}
    names = {'filesystem', 'linux', 'glibc', 'binutils'}
    for record in index['packages']:
        name = record['identity']['name']
        if name in names:
            if name in selected:
                raise PackageError(f'ambiguous native linker seed identity: {name}')
            selected[name] = record
    if set(selected) != names:
        raise PackageError('native linker seed requires four published packages')
    versions = {'filesystem': '1', 'linux': '7.1.8',
                'glibc': '2.44', 'binutils': '2.47'}
    for name, version in versions.items():
        identity = selected[name]['identity']
        if (identity['version'] != version or identity['architecture'] != 'x86_64'
                or type(identity['revision']) is not int or identity['revision'] < 1):
            raise PackageError(f'invalid native linker seed identity: {name}')
    expected_relationships = {
        'filesystem': [],
        'linux': [{'name': 'filesystem', 'version': '1'}],
        'glibc': [{'name': 'filesystem', 'version': '1'},
                  {'name': 'linux', 'version': '7.1.8'}],
        'binutils': [{'name': 'filesystem', 'version': '1'},
                     {'name': 'glibc', 'version': '2.44'}],
    }
    for name, relationships in expected_relationships.items():
        if selected[name]['relationships'] != relationships:
            raise PackageError(f'native linker seed relationships differ: {name}')
    # Preserve dependency order: filesystem first; the two independent
    # prerequisites before Binutils. Manage still owns all installation IO.
    ordered = tuple(selected[name] for name in
                    ('filesystem', 'linux', 'glibc', 'binutils'))
    canonical_claims(list(ordered))
    return ordered


def install_native_linker_seed(repo: Path, destination: Path) -> Path:
    """Manage-install the unaccepted four-package native linker seed."""
    return _install_selected(repo, destination, resolve_native_linker_seed(repo),
                             status='native-linker-seed-not-accepted',
                             selection='filesystem+linux+glibc+binutils')


def resolve_native_compiler_seed(repo: Path) -> tuple[dict, ...]:
    """Select exactly the published five-package compiler bootstrap closure.

    This is not a runnable native buildroot: Bash, Make, Coreutils and other
    tools remain absent. No Stage 1B file is imported into this root.
    """
    base = resolve_native_linker_seed(repo)
    index = verify_repository(repo)
    gcc = [r for r in index['packages'] if r['identity']['name'] == 'gcc']
    if len(gcc) != 1:
        raise PackageError('native compiler seed needs exactly one GCC artifact')
    compiler = gcc[0]
    ident = compiler['identity']
    if (ident['version'] != '16.2.0' or ident['architecture'] != 'x86_64'
            or type(ident['revision']) is not int or ident['revision'] != 1):
        raise PackageError('native compiler seed GCC identity mismatch')
    expected = [
        {'name': 'binutils', 'version': '2.47'},
        {'name': 'filesystem', 'version': '1'},
        {'name': 'glibc', 'version': '2.44'},
        {'name': 'linux', 'version': '7.1.8'},
    ]
    if compiler['relationships'] != expected:
        raise PackageError('native compiler seed GCC relationships mismatch')
    selected = (*base, compiler)
    canonical_claims(list(selected))
    return selected


def install_native_compiler_seed(repo: Path, destination: Path) -> Path:
    """Manage-install the exact five-package seed, without claiming closure."""
    return _install_selected(repo, destination, resolve_native_compiler_seed(repo),
                             status='native-compiler-seed-not-accepted',
                             selection='filesystem+linux+glibc+binutils+gcc')
