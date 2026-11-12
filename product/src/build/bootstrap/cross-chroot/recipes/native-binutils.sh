#!/usr/bin/env bash
set -euo pipefail
: "${DISTRO_SOURCE_DIR:?}" "${DISTRO_ROOT_DIR:?}" "${DISTRO_TARGET:?}" "${DISTRO_JOBS:?}"
export CC="/toolchain/tools/bin/${DISTRO_TARGET}-gcc --sysroot=/toolchain -fno-link-libatomic"
export CFLAGS=-O2
export LDFLAGS='-B/toolchain/usr/lib64/ -L/toolchain/usr/lib64 -L/toolchain/lib64'
"$DISTRO_SOURCE_DIR/configure" --build=x86_64-pc-linux-gnu --host="$DISTRO_TARGET" --target="$DISTRO_TARGET" --prefix=/usr --disable-nls --disable-werror --disable-gdb --disable-gprofng --disable-sim
make -j"$DISTRO_JOBS"
make install DESTDIR="$DISTRO_ROOT_DIR"
