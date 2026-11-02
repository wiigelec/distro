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
# Build is responsible for preparing verified gmp/, mpfr/, and mpc/ inside
# this step's private, freshly extracted GCC source tree.
for lib in gmp mpfr mpc; do
  [[ -d "$DISTRO_SOURCE_DIR/$lib" ]] || { echo "verified $lib source not prepared" >&2; exit 2; }
done
"$DISTRO_SOURCE_DIR/configure" \
  --target="$DISTRO_TARGET" --prefix="$DISTRO_TOOLS_DIR" \
  --with-sysroot="$DISTRO_ROOT_DIR" \
  --with-newlib --without-headers --enable-default-pie \
  --disable-nls --disable-shared --disable-multilib \
  --disable-threads --disable-libatomic --disable-libgomp \
  --disable-libquadmath --disable-libssp --disable-libvtv \
  --disable-libstdcxx --enable-languages=c,c++
make -j"$JOBS" all-gcc
make -j"$JOBS" all-target-libgcc
make install-gcc
make install-target-libgcc
"$DISTRO_TOOLS_DIR/bin/$DISTRO_TARGET-gcc" --version
