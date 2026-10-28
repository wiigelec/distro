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
# Build must supply a distinct pristine GCC extraction, never GCC pass-1's tree.
# gcc/libstdc++-v3's standalone configure is the Stage 1A library phase.
[[ -f "$DISTRO_SOURCE_DIR/libstdc++-v3/configure" ]] || { echo 'missing libstdc++ source' >&2; exit 2; }
"$DISTRO_SOURCE_DIR/libstdc++-v3/configure" \
  --host="$DISTRO_TARGET" --build="$(gcc -dumpmachine)" \
  --prefix=/usr --disable-multilib --disable-nls \
  --disable-nls
make -j"$JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
