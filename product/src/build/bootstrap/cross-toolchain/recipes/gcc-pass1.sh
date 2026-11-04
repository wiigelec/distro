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

# FS-001 #6: GCC was built without libc headers. After installing pass 1,
# assemble the target-aware limits.h so it can include glibc's limits.h when
# target libc is installed. See LFS GCC Pass 1; do not use mkheaders.
for fragment in limitx.h glimits.h limity.h; do
  [[ -f "$DISTRO_SOURCE_DIR/gcc/$fragment" && ! -L "$DISTRO_SOURCE_DIR/gcc/$fragment" ]] || {
    echo "missing regular GCC limits fragment: $fragment" >&2; exit 1;
  }
done
compiler="$DISTRO_TOOLS_DIR/bin/$DISTRO_TARGET-gcc"
libgcc_file="$("$compiler" -print-libgcc-file-name)"
private_dir="$(dirname -- "$libgcc_file")"
expected_dir="$DISTRO_TOOLS_DIR/lib/gcc/$DISTRO_TARGET/$DISTRO_PACKAGE_VERSION"
[[ "$private_dir" == "$expected_dir" && -d "$private_dir/include" && ! -L "$private_dir/include" ]] || {
  echo "unexpected GCC private header path: $private_dir" >&2; exit 1;
}
limits="$private_dir/include/limits.h"
[[ -f "$limits" && ! -L "$limits" ]] || { echo 'unexpected GCC limits.h target' >&2; exit 1; }
tmp="$(mktemp "$private_dir/include/.limits.h.XXXXXXXX")"
trap 'rm -f -- "$tmp"' EXIT
cat -- "$DISTRO_SOURCE_DIR/gcc/limitx.h" "$DISTRO_SOURCE_DIR/gcc/glimits.h" \
  "$DISTRO_SOURCE_DIR/gcc/limity.h" > "$tmp"
grep -q '#include_next' "$tmp" || { echo 'GCC limits.h lacks include_next' >&2; exit 1; }
chmod --reference="$limits" "$tmp"
mv -f -- "$tmp" "$limits"
trap - EXIT
