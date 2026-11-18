#!/usr/bin/env bash
set -euo pipefail
: "${DISTRO_SOURCE_DIR:?}" "${DISTRO_BUILD_DIR:?}" "${DISTRO_ROOT_DIR:?}" "${DISTRO_TARGET:?}" "${DISTRO_JOBS:?}"
# FS-002 Issue #17: Stage 1B bootstrap-only local-file rsync capability.
# Use authenticated Stage 1A compiler/sysroot; no target library prerequisites
# beyond imported libc. Optional external libraries are deliberately omitted.
export CC="/toolchain/tools/bin/${DISTRO_TARGET}-gcc --sysroot=/toolchain -fno-link-libatomic"
export CXX="/toolchain/tools/bin/${DISTRO_TARGET}-g++ --sysroot=/toolchain -fno-link-libatomic"
export AR="/toolchain/tools/bin/${DISTRO_TARGET}-ar"
export RANLIB="/toolchain/tools/bin/${DISTRO_TARGET}-ranlib"
export CFLAGS=-O2
export LDFLAGS='-B/toolchain/usr/lib64/ -L/toolchain/usr/lib64 -L/toolchain/lib64'
cd "$DISTRO_BUILD_DIR"
"$DISTRO_SOURCE_DIR/configure" \
  --host="$DISTRO_TARGET" --build=x86_64-pc-linux-gnu \
  --prefix=/usr --disable-md2man --disable-openssl \
  --disable-xxhash --disable-zstd --disable-lz4 \
  --disable-simd --disable-acl-support --disable-xattr-support \
  --disable-iconv --disable-idn --with-included-zlib --with-included-popt
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
[[ -x "$DISTRO_ROOT_DIR/usr/bin/rsync" ]]
