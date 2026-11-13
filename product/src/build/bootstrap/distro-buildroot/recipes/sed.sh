#!/usr/bin/env bash
set -euo pipefail

# Runs only inside Build's isolated target-native execution environment.
# The construction root must remain read-only; DESTDIR is a separate stage.
: "${DISTRO_SOURCE_DIR:?missing verified source directory}"
: "${DISTRO_BUILD_DIR:?missing build directory}"
: "${DISTRO_ROOT_DIR:?missing isolated package staging destination}"
: "${DISTRO_JOBS:?missing bounded build parallelism}"

cd "$DISTRO_BUILD_DIR"
"$DISTRO_SOURCE_DIR/configure" --prefix=/usr
make -j"$DISTRO_JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
