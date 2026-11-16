#!/usr/bin/env bash
set -euo pipefail
# FS-004 stage-specific target-native recipe. Never executes on the host.
: "${DISTRO_SOURCE_DIR:?missing verified source directory}"
: "${DISTRO_BUILD_DIR:?missing build directory}"
: "${DISTRO_ROOT_DIR:?missing independent stage directory}"
: "${DISTRO_JOBS:?missing bounded parallelism}"
cd "$DISTRO_BUILD_DIR"
# Target-native libc, not a Stage 1A cross-compiler recipe.
"$DISTRO_SOURCE_DIR/configure" --prefix=/usr --disable-werror --with-headers=/usr/include
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
