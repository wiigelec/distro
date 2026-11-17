#!/usr/bin/env bash
set -euo pipefail
: "${DISTRO_SOURCE_DIR:?}" "${DISTRO_BUILD_DIR:?}" "${DISTRO_ROOT_DIR:?}" "${DISTRO_TARGET:?}" "${DISTRO_JOBS:?}"
# Build-side Python is compiled from the SAME sha256-verified CPython source,
# exclusively inside /work. Never stage it or mount it in a native FS-004 run.
mkdir -p "$DISTRO_BUILD_DIR/build-python" "$DISTRO_BUILD_DIR/target-python"
cd "$DISTRO_BUILD_DIR/build-python"
env CC=/usr/bin/gcc CXX=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib \
  "$DISTRO_SOURCE_DIR/configure" --build=x86_64-pc-linux-gnu --prefix=/work/fs002-build-python --without-ensurepip --disable-test-modules
make -j"$DISTRO_JOBS" python
[[ -x "$PWD/python" ]]
build_python="$PWD/python"
"$build_python" -c 'import sys; assert sys.version_info[:3] == (3,13,11)'
cd "$DISTRO_BUILD_DIR/target-python"
export CC="/toolchain/tools/bin/${DISTRO_TARGET}-gcc --sysroot=/toolchain -fno-link-libatomic"
export CXX="/toolchain/tools/bin/${DISTRO_TARGET}-g++ --sysroot=/toolchain -fno-link-libatomic"
export AR="/toolchain/tools/bin/${DISTRO_TARGET}-ar"
export RANLIB="/toolchain/tools/bin/${DISTRO_TARGET}-ranlib"
export CFLAGS=-O2 LDFLAGS='-B/toolchain/usr/lib64/ -L/toolchain/usr/lib64 -L/toolchain/lib64'
# CPython documents this cache answer for cross builds: the isolated
# target probe cannot execute its test binary. Native smoke verifies
# Python after installation and again after independent relocation.
export ac_cv_file__dev_ptmx=yes ac_cv_file__dev_ptc=no ac_cv_buggy_getaddrinfo=no
"$DISTRO_SOURCE_DIR/configure" --build=x86_64-pc-linux-gnu --host="$DISTRO_TARGET" \
  --prefix=/usr --with-build-python="$build_python" --without-ensurepip --disable-test-modules
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
[[ -x "$DISTRO_ROOT_DIR/usr/bin/python3.13" ]]
# The target /usr/bin/python3 must be part of the *staged* payload.
[[ -e "$DISTRO_ROOT_DIR/usr/bin/python3" || -L "$DISTRO_ROOT_DIR/usr/bin/python3" ]]
