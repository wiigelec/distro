#!/usr/bin/env bash
set -euo pipefail
# FS-004 stage-specific target-native recipe. Never executes on the host.
: "${DISTRO_SOURCE_DIR:?missing verified source directory}"
: "${DISTRO_BUILD_DIR:?missing build directory}"
: "${DISTRO_ROOT_DIR:?missing independent stage directory}"
: "${DISTRO_JOBS:?missing bounded parallelism}"
# Only the selected, independently Manage-installed linker seed supplies
# new Binutils, kernel headers, and Glibc. Stage 1B supplies the bootstrap
# compiler and make; the four-package seed is not a runnable Build root.
: "${DISTRO_NATIVE_LINKER_ROOT:?missing authenticated native linker seed}"
seed="$DISTRO_NATIVE_LINKER_ROOT"
for tool in as ld; do
    [[ -x "$seed/usr/bin/$tool" ]] || {
        echo "selected native Binutils $tool unavailable" >&2; exit 1;
    }
done
[[ -d "$seed/usr/include/linux" && -d "$seed/usr/include/asm-generic" ]] || {
    echo 'selected native Linux headers unavailable' >&2; exit 1;
}
for part in crti.o crtn.o libc.so libc_nonshared.a ld-linux-x86-64.so.2; do
    [[ -f "$seed/usr/lib/$part" ]] || {
        echo "selected native Glibc missing $part" >&2; exit 1;
    }
done
# The chosen assembler/linker must precede Stage 1B tool paths. GCC invokes
# them through -B, while the native seed sysroot supplies libc and headers.
export CC="gcc --sysroot=$seed -B$seed/usr/bin/ -B$seed/usr/lib/"
export CXX="g++ --sysroot=$seed -B$seed/usr/bin/ -B$seed/usr/lib/"
export AS="$seed/usr/bin/as" LD="$seed/usr/bin/ld"
export CPPFLAGS="-isystem $seed/usr/include ${CPPFLAGS:-}"
export LDFLAGS="-L$seed/usr/lib -Wl,-rpath-link,$seed/usr/lib -Wl,--dynamic-linker=/lib64/ld-linux-x86-64.so.2 ${LDFLAGS:-}"
cd "$DISTRO_BUILD_DIR"
# The verified source directory contains selected GMP, MPFR and MPC trees.
for library in gmp mpfr mpc; do
    [[ -d "$DISTRO_SOURCE_DIR/$library" ]] || { echo "missing GCC $library supplement" >&2; exit 1; }
done
"$DISTRO_SOURCE_DIR/configure" --prefix=/usr --disable-multilib --disable-bootstrap --enable-languages=c,c++ --disable-nls --with-native-system-header-dir=/usr/include --without-isl
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
