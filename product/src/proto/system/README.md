# Minimal managed userspace prototype

This prototype crosses the Build -> Package Database -> Manage boundary.

The milestone is:

```text
Build musl
Build base-files
Build BusyBox dynamically against musl
    |
    v
prototype repository
    |- database.json
    `- packages/*.distro.tar.gz
    |
    v
Manage install busybox --root ROOT
    |
    +-> resolve busybox -> musl + base-files
    +-> verify artifact SHA-256
    +-> verify embedded identity
    +-> validate owned-path inventory/conflicts
    +-> install musl as dependency
    +-> install base-files as dependency
    +-> install busybox as explicit
    `-> write ROOT/var/lib/distro/manage/installed.json
    |
    v
chroot ROOT /bin/sh
    |
    v
ls /
```

The fixture is x86_64-only and pins musl 1.2.3, base-files 1.0.0, and BusyBox 1.37.0.
The build environment is `debian:12-slim`. BusyBox is dynamically linked with
Debian's `musl-gcc`; the musl package itself is built from matching upstream
1.2.3 source.

This is a package-management prototype, not the finalized bootstrap policy or
source/version-discovery path.

## Build the repository

```sh
python3 product/src/proto/builder/system_fixture.py \
  --output /tmp/distro-system-repo
```

## Install BusyBox into an empty root

```sh
sudo rm -rf /tmp/distro-root

python3 product/src/proto/manager/manage.py install \
  --repository /tmp/distro-system-repo \
  --root /tmp/distro-root \
  busybox
```

Manage resolves `busybox -> musl + base-files`, verifies all artifacts before
payload application, preflights owned-path conflicts, applies dependencies first, and
writes target-root-local installed state.

## Verify the root

```sh
python3 product/src/proto/system/acceptance.py \
  --root /tmp/distro-root
```

Expected reasons:

```text
busybox     explicit
base-files  dependency
musl        dependency
```

## Chroot smoke test

```sh
sudo chroot /tmp/distro-root /bin/sh -l
```

Inside:

```sh
ls /
exit
```

Success means `/bin/sh` starts as a login shell under the installed musl runtime,
`base-files` initializes `PATH` through `/etc/profile`, and BusyBox provides `ls`
from the filesystem assembled by Manage.

## Prototype limits

Manage v0 supports only install, one identity per package name, unconstrained
package-name dependencies, artifact SHA-256 verification, embedded identity
verification, owned-file/symlink conflict detection, and target-root-local
installed state.

Removal, upgrade, version constraints, capability-provider solving, repository
refresh, holds, rollback, mutable configuration handling, and lifecycle scripts
are outside this milestone.
