#!/usr/bin/env bash
set -euo pipefail
: "${DISTRO_SOURCE_DIR:?}" "${DISTRO_BUILD_DIR:?}" "${DISTRO_ROOT_DIR:?}" "${DISTRO_TARGET:?}" "${DISTRO_JOBS:?}"
# Stage 1B target utilities are cross-compiled from the authenticated Stage 1A sysroot.
export CC="/toolchain/tools/bin/${DISTRO_TARGET}-gcc --sysroot=/toolchain -fno-link-libatomic"
export CXX="/toolchain/tools/bin/${DISTRO_TARGET}-g++ --sysroot=/toolchain -fno-link-libatomic"
export AR="/toolchain/tools/bin/${DISTRO_TARGET}-ar"
export RANLIB="/toolchain/tools/bin/${DISTRO_TARGET}-ranlib"
export CFLAGS=-O2
export LDFLAGS='-B/toolchain/usr/lib64/ -L/toolchain/usr/lib64 -L/toolchain/lib64'
cd "$DISTRO_BUILD_DIR"
"$DISTRO_SOURCE_DIR/configure" --host="$DISTRO_TARGET" --build=x86_64-pc-linux-gnu --prefix=/usr --disable-nls
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
[[ -x "$DISTRO_ROOT_DIR/usr/bin/find" && -x "$DISTRO_ROOT_DIR/usr/bin/xargs" ]]
