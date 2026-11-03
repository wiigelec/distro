#!/usr/bin/env bash
set -euo pipefail
: "${DISTRO_SOURCE_DIR:?}" "${DISTRO_BUILD_DIR:?}" "${DISTRO_ROOT_DIR:?}" "${DISTRO_TARGET:?}" "${DISTRO_JOBS:?}"
export CC="/toolchain/tools/bin/${DISTRO_TARGET}-gcc --sysroot=/toolchain -fno-link-libatomic"
export CXX="/toolchain/tools/bin/${DISTRO_TARGET}-g++ --sysroot=/toolchain -fno-link-libatomic"
export AR="/toolchain/tools/bin/${DISTRO_TARGET}-ar"
export RANLIB="/toolchain/tools/bin/${DISTRO_TARGET}-ranlib"
export CFLAGS=-O2
export LDFLAGS='-B/toolchain/usr/lib64/ -L/toolchain/usr/lib64 -L/toolchain/lib64'
"$DISTRO_SOURCE_DIR/configure" --host="$DISTRO_TARGET" --build=x86_64-pc-linux-gnu --prefix=/usr --disable-nls --without-selinux
make -j"$DISTRO_JOBS"
make install DESTDIR="$DISTRO_ROOT_DIR"
# GNU install-info creates a shared, derived Info directory index.  The
# imported glibc index is already owned by FS-001, so it must not be replaced
# by the Coreutils-only index generated in this isolated DESTDIR.  Retain the
# package-specific .info documentation; Info menu regeneration belongs to a
# later, explicitly governed target-system step.
info_dir="$DISTRO_ROOT_DIR/usr/share/info/dir"
if [[ -e "$info_dir" || -L "$info_dir" ]]; then
    [[ -f "$info_dir" && ! -L "$info_dir" ]] || {
        echo "unexpected Coreutils staged Info index type: $info_dir" >&2
        exit 1
    }
    rm -- "$info_dir"
fi
