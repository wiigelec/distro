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
"$DISTRO_SOURCE_DIR/configure" \
  --prefix="$DISTRO_TOOLS_DIR" --target="$DISTRO_TARGET" \
  --with-sysroot="$DISTRO_ROOT_DIR" --disable-nls --enable-gprofng=no \
  --disable-werror
make -j"$JOBS"
make install
"$DISTRO_TOOLS_DIR/bin/$DISTRO_TARGET-as" --version
"$DISTRO_TOOLS_DIR/bin/$DISTRO_TARGET-ld" --version
