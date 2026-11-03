#!/usr/bin/env bash
set -euo pipefail
: "${DISTRO_SOURCE_DIR:?}" "${DISTRO_BUILD_DIR:?}" "${DISTRO_ROOT_DIR:?}" "${DISTRO_TARGET:?}" "${DISTRO_JOBS:?}"
export CC="/toolchain/tools/bin/${DISTRO_TARGET}-gcc --sysroot=/toolchain -fno-link-libatomic"
export CXX="/toolchain/tools/bin/${DISTRO_TARGET}-g++ --sysroot=/toolchain -fno-link-libatomic"
export AR="/toolchain/tools/bin/${DISTRO_TARGET}-ar"
export RANLIB="/toolchain/tools/bin/${DISTRO_TARGET}-ranlib"
export CFLAGS=-O2
export LDFLAGS='-B/toolchain/usr/lib64/ -L/toolchain/usr/lib64 -L/toolchain/lib64'
"$DISTRO_SOURCE_DIR/configure" --host="$DISTRO_TARGET" --build=x86_64-pc-linux-gnu --prefix=/usr --disable-nls --without-bash-malloc --bindir=/usr/bin
make -j"$DISTRO_JOBS"
make install DESTDIR="$DISTRO_ROOT_DIR"
# The GNU Info "dir" index is shared, not owned by Bash. Keep the imported
# index unchanged; remove only Bash's newly generated staged regular file.
info_index="$DISTRO_ROOT_DIR/usr/share/info/dir"
if [[ -e "$info_index" || -L "$info_index" ]]; then
  if [[ ! -f "$info_index" || -L "$info_index" ]]; then
    echo "refusing unexpected staged Info directory index type" >&2
    exit 1
  fi
  rm -- "$info_index"
fi
if [[ -e "$DISTRO_ROOT_DIR/usr/bin/sh" || -L "$DISTRO_ROOT_DIR/usr/bin/sh" ]]; then
  echo "refusing to replace existing /usr/bin/sh" >&2
  exit 1
fi
ln -s bash "$DISTRO_ROOT_DIR/usr/bin/sh"
