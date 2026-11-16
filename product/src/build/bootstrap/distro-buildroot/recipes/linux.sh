#!/usr/bin/env bash
set -euo pipefail
# FS-004 stage-specific target-native recipe. Never executes on the host.
: "${DISTRO_SOURCE_DIR:?missing verified source directory}"
: "${DISTRO_BUILD_DIR:?missing build directory}"
: "${DISTRO_ROOT_DIR:?missing independent stage directory}"
: "${DISTRO_JOBS:?missing bounded parallelism}"
cd "$DISTRO_BUILD_DIR"
# Headers-only package; no kernel build or target boot installation.
make -C "$DISTRO_SOURCE_DIR" mrproper
make -C "$DISTRO_SOURCE_DIR" headers
make -C "$DISTRO_SOURCE_DIR" INSTALL_HDR_PATH="$DISTRO_ROOT_DIR/usr" headers_install
