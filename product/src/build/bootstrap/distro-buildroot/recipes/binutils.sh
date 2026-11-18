#!/usr/bin/env bash
set -euo pipefail
# FS-004 stage-specific target-native recipe. Never executes on the host.
: "${DISTRO_SOURCE_DIR:?missing verified source directory}"
: "${DISTRO_BUILD_DIR:?missing build directory}"
: "${DISTRO_ROOT_DIR:?missing independent stage directory}"
: "${DISTRO_JOBS:?missing bounded parallelism}"
# Stage 1B supplies the executable compiler only. Headers, libc linker
# script, startup objects and runtime loader must come from the independently
# Manage-installed and authenticated native seed, never implicit Stage 1B paths.
: "${DISTRO_NATIVE_SEED_ROOT:?missing Manage-installed native toolchain seed}"
seed="$DISTRO_NATIVE_SEED_ROOT"
[[ -d "$seed/usr/include/linux" && -d "$seed/usr/include/asm-generic" ]] || {
    echo "selected Linux UAPI headers missing from managed sysroot" >&2; exit 1;
}
for part in crt1.o crti.o crtn.o libc.so libc_nonshared.a ld-linux-x86-64.so.2; do
    [[ -f "$seed/usr/lib/$part" ]] || {
        echo "selected Glibc sysroot missing $part" >&2; exit 1;
    }
done
# --sysroot controls implicit system header/library searches, while -B
# explicitly selects the Glibc startup objects for both compiler drivers.
# The runtime interpreter path is an in-target name; the merged-/usr layout
# resolves /lib64 to /usr/lib in the eventual Manage-installed root.
export CC="gcc --sysroot=$seed -B$seed/usr/lib/"
export CXX="g++ --sysroot=$seed -B$seed/usr/lib/"
export CPPFLAGS="-isystem $seed/usr/include ${CPPFLAGS:-}"
export LDFLAGS="-L$seed/usr/lib -Wl,-rpath-link,$seed/usr/lib -Wl,--dynamic-linker=/lib64/ld-linux-x86-64.so.2 ${LDFLAGS:-}"
cd "$DISTRO_BUILD_DIR"
# gprofng is an optional profiler, not required for the selected native
# assembler/linker tools. Its C++ build currently fails on isolated headers;
# exclude it explicitly rather than weakening the verified sysroot.
"$DISTRO_SOURCE_DIR/configure" --prefix=/usr --disable-nls --disable-werror \
  --disable-gprofng --enable-shared
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
