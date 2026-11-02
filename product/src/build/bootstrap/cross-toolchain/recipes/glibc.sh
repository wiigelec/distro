#!/usr/bin/env bash
set -euo pipefail
: "${DISTRO_SOURCE_DIR:?}"
: "${DISTRO_BUILD_DIR:?}"
: "${DISTRO_ROOT_DIR:?}"
: "${DISTRO_TOOLS_DIR:?}"
: "${DISTRO_TARGET:?}"
: "${DISTRO_PACKAGE_VERSION:?}"
[[ "$DISTRO_SOURCE_DIR" == /work/* && "$DISTRO_BUILD_DIR" == /work/* ]] || { echo 'source/build outside /work' >&2; exit 2; }
[[ "$DISTRO_ROOT_DIR" == /toolchain && "$DISTRO_TOOLS_DIR" == /toolchain/tools ]] || { echo 'incorrect target mount contract' >&2; exit 2; }
[[ -d "$DISTRO_SOURCE_DIR" && -d "$DISTRO_BUILD_DIR" ]] || { echo 'source/build directory missing' >&2; exit 2; }
cd "$DISTRO_BUILD_DIR"
JOBS="${DISTRO_JOBS:-1}"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo 'invalid DISTRO_JOBS' >&2; exit 2; }
# This recipe intentionally downloads no LFS patch and applies no implicit patch.
# Build failures must be diagnosed before a separately reviewed local patch is added.
BUILD_TRIPLET="$(gcc -dumpmachine)"
[[ -n "$BUILD_TRIPLET" ]] || { echo 'host GCC triplet missing' >&2; exit 2; }
"$DISTRO_SOURCE_DIR/configure" \
  --prefix=/usr --host="$DISTRO_TARGET" --build="$BUILD_TRIPLET" \
  --enable-kernel=5.4 --with-headers="$DISTRO_ROOT_DIR/usr/include" \
  --disable-nscd --disable-werror \
  "libc_cv_slibdir=/usr/lib"
make -j"$JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
[[ -f "$DISTRO_ROOT_DIR/usr/lib/libc.so.6" || -f "$DISTRO_ROOT_DIR/lib64/libc.so.6" ]]
