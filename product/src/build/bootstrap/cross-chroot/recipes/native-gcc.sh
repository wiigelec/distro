#!/usr/bin/env bash
set -euo pipefail
: "${DISTRO_SOURCE_DIR:?}" "${DISTRO_ROOT_DIR:?}" "${DISTRO_TARGET:?}" "${DISTRO_JOBS:?}"
export CC="/toolchain/tools/bin/${DISTRO_TARGET}-gcc --sysroot=/toolchain -fno-link-libatomic"
export CXX="/toolchain/tools/bin/${DISTRO_TARGET}-g++ --sysroot=/toolchain -fno-link-libatomic"
export CC_FOR_BUILD=/usr/bin/gcc CXX_FOR_BUILD=/usr/bin/g++
export CFLAGS=-O2 CXXFLAGS=-O2
export CFLAGS_FOR_TARGET='-O2 -fno-link-libatomic'
export CXXFLAGS_FOR_TARGET='-O2 -fno-link-libatomic'
export gcc_cv_sys_sdt_h=no
export LDFLAGS='-B/toolchain/usr/lib64/ -L/toolchain/usr/lib64 -L/toolchain/lib64'
"$DISTRO_SOURCE_DIR/configure" --build=x86_64-pc-linux-gnu --host="$DISTRO_TARGET" --target="$DISTRO_TARGET" --prefix=/usr --with-build-sysroot=/toolchain --with-native-system-header-dir=/usr/include --without-isl --without-zstd --disable-bootstrap --disable-multilib --disable-fixincludes --disable-nls --disable-libsanitizer --disable-libssp --disable-libquadmath --disable-libgomp --disable-libatomic --enable-languages=c,c++
make -j"$DISTRO_JOBS"
# Match FS-001's merged-/usr layout *before* GCC installs runtime libraries.
# This is the isolated DESTDIR staging root, never the imported toolchain.
mkdir -p "$DISTRO_ROOT_DIR/usr/lib"
if [ -e "$DISTRO_ROOT_DIR/usr/lib64" ] || [ -L "$DISTRO_ROOT_DIR/usr/lib64" ]; then
    echo "native GCC stage usr/lib64 must not preexist" >&2
    exit 1
fi
ln -s lib "$DISTRO_ROOT_DIR/usr/lib64"
make install DESTDIR="$DISTRO_ROOT_DIR"
