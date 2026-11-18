#!/usr/bin/env bash
set -euo pipefail
# FS-004 selected target-native recipe; runs only in the isolated native executor.
: "${DISTRO_SOURCE_DIR:?missing verified source directory}"
: "${DISTRO_BUILD_DIR:?missing build directory}"
: "${DISTRO_ROOT_DIR:?missing independent stage directory}"
: "${DISTRO_JOBS:?missing bounded parallelism}"
cd "$DISTRO_BUILD_DIR"
# Use included dependencies; never infer host optional-library availability.
"$DISTRO_SOURCE_DIR/configure" --prefix=/usr --disable-md2man --disable-openssl \
  --disable-xxhash --disable-zstd --disable-lz4 --disable-simd \
  --disable-acl-support --disable-xattr-support --disable-iconv \
  --disable-idn --with-included-zlib --with-included-popt
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
[[ -x "$DISTRO_ROOT_DIR/usr/bin/rsync" ]]
