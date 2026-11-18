#!/usr/bin/env bash
set -euo pipefail
# FS-004 selected target-native recipe; runs only in the isolated native executor.
: "${DISTRO_SOURCE_DIR:?missing verified source directory}"
: "${DISTRO_BUILD_DIR:?missing build directory}"
: "${DISTRO_ROOT_DIR:?missing independent stage directory}"
: "${DISTRO_JOBS:?missing bounded parallelism}"
cd "$DISTRO_BUILD_DIR"
# Native construction uses the authenticated selected toolchain; no
# separately constructed host interpreter or host-userspace mount.
"$DISTRO_SOURCE_DIR/configure" --prefix=/usr --without-ensurepip \
  --disable-test-modules --with-pkg-config=no
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
[[ -x "$DISTRO_ROOT_DIR/usr/bin/python3.13" ]]
