#!/usr/bin/env bash
set -euo pipefail
# FS-004 stage-specific target-native recipe. Never executes on the host.
: "${DISTRO_SOURCE_DIR:?missing verified source directory}"
: "${DISTRO_BUILD_DIR:?missing build directory}"
: "${DISTRO_ROOT_DIR:?missing independent stage directory}"
: "${DISTRO_JOBS:?missing bounded parallelism}"
# Explicitly consume the selected Manage-installed native headers and libc
# search path. The Stage 1B compiler remains the authenticated bootstrap tool.
: "${DISTRO_NATIVE_SEED_ROOT:?missing Manage-installed native toolchain seed}"
[[ -d "$DISTRO_NATIVE_SEED_ROOT/usr/include/linux" &&
   -d "$DISTRO_NATIVE_SEED_ROOT/usr/lib" ]] || {
    echo "selected native seed headers and libraries missing" >&2; exit 1;
}
export CPPFLAGS="-I$DISTRO_NATIVE_SEED_ROOT/usr/include ${CPPFLAGS:-}"
export LDFLAGS="-L$DISTRO_NATIVE_SEED_ROOT/usr/lib ${LDFLAGS:-}"
cd "$DISTRO_BUILD_DIR"
"$DISTRO_SOURCE_DIR/configure" --prefix=/usr --disable-nls --disable-werror --enable-shared
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
