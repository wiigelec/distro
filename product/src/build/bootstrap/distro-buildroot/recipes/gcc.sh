#!/usr/bin/env bash
set -euo pipefail
# FS-004 stage-specific target-native recipe. Never executes on the host.
: "${DISTRO_SOURCE_DIR:?missing verified source directory}"
: "${DISTRO_BUILD_DIR:?missing build directory}"
: "${DISTRO_ROOT_DIR:?missing independent stage directory}"
: "${DISTRO_JOBS:?missing bounded parallelism}"
cd "$DISTRO_BUILD_DIR"
# The verified source directory contains selected GMP, MPFR and MPC trees.
for library in gmp mpfr mpc; do
    [[ -d "$DISTRO_SOURCE_DIR/$library" ]] || { echo "missing GCC $library supplement" >&2; exit 1; }
done
"$DISTRO_SOURCE_DIR/configure" --prefix=/usr --disable-multilib --disable-bootstrap --enable-languages=c,c++ --disable-nls
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
