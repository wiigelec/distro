#!/usr/bin/env bash
set -euo pipefail
# FS-004 stage-specific target-native recipe. Never executes on the host.
: "${DISTRO_SOURCE_DIR:?missing verified source directory}"
: "${DISTRO_BUILD_DIR:?missing build directory}"
: "${DISTRO_ROOT_DIR:?missing independent stage directory}"
: "${DISTRO_JOBS:?missing bounded parallelism}"
cd "$DISTRO_BUILD_DIR"
# Target-native libc, not a Stage 1A cross-compiler recipe.
: "${DISTRO_LINUX_HEADERS_DIR:?missing Manage-installed Linux headers mount}"
[[ -d "$DISTRO_LINUX_HEADERS_DIR/linux" && -d "$DISTRO_LINUX_HEADERS_DIR/asm-generic" ]] || {
    echo "selected Linux headers missing from native construction mount" >&2; exit 1;
}
"$DISTRO_SOURCE_DIR/configure" --prefix=/usr --disable-werror --with-headers="$DISTRO_LINUX_HEADERS_DIR"
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
