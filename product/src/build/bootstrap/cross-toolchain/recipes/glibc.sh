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
# This recipe intentionally downloads no LFS patch and applies no implicit patch.
# Build failures must be diagnosed before a separately reviewed local patch is added.
BUILD_TRIPLET="$(gcc -dumpmachine)"
[[ -n "$BUILD_TRIPLET" ]] || { echo 'host GCC triplet missing' >&2; exit 2; }
# FS-001 Issue #8: Arch x86-64 merged-/usr layout. All targets are relative,
# with /usr/lib the canonical native library location. This is a fresh root;
# no pre-existing entry may be overwritten or migrated implicitly.
[[ -d "$DISTRO_ROOT_DIR/usr" && ! -L "$DISTRO_ROOT_DIR/usr" ]] || {
  echo 'missing real /usr directory in target root' >&2; exit 1;
}
for name in bin lib; do
  path="$DISTRO_ROOT_DIR/usr/$name"
  if [[ -e "$path" || -L "$path" ]]; then
    [[ -d "$path" && ! -L "$path" ]] || {
      echo "conflicting canonical /usr/$name entry" >&2; exit 1;
    }
  else
    mkdir -- "$path"
  fi
done
for entry in \
  'bin:usr/bin' \
  'sbin:usr/bin' \
  'lib:usr/lib' \
  'lib64:usr/lib' \
  'usr/sbin:bin' \
  'usr/lib64:lib'; do
  name="${entry%%:*}"
  target="${entry#*:}"
  link="$DISTRO_ROOT_DIR/$name"
  if [[ -e "$link" || -L "$link" ]]; then
    echo "conflicting merged-/usr entry: $name" >&2; exit 1;
  fi
  ln -s -- "$target" "$link"
done
"$DISTRO_SOURCE_DIR/configure" \
  --prefix=/usr --host="$DISTRO_TARGET" --build="$BUILD_TRIPLET" \
  --enable-kernel=5.4 --with-headers="$DISTRO_ROOT_DIR/usr/include" \
  --disable-nscd --disable-werror \
  "libc_cv_slibdir=/usr/lib"
make -j"$JOBS"
make DESTDIR="$DISTRO_ROOT_DIR" install
for name in libc.so.6 ld-linux-x86-64.so.2; do
  [[ -f "$DISTRO_ROOT_DIR/usr/lib/$name" && ! -L "$DISTRO_ROOT_DIR/usr/lib/$name" ]] || {
    echo "missing canonical glibc runtime: /usr/lib/$name" >&2; exit 1;
  }
done
for entry in 'lib:usr/lib' 'lib64:usr/lib' 'usr/lib64:lib'; do
  name="${entry%%:*}"; target="${entry#*:}"
  [[ -L "$DISTRO_ROOT_DIR/$name" && "$(readlink -- "$DISTRO_ROOT_DIR/$name")" == "$target" ]] || {
    echo "glibc changed target layout: $name" >&2; exit 1;
  }
done

# FS-001 #6: glibc's fortified headers must agree with GCC private limits.h.
# Compile only: do not execute target code in the host sandbox.
probe="$DISTRO_BUILD_DIR/fs001-limits-probe.c"
object="$DISTRO_BUILD_DIR/fs001-limits-probe.o"
cat > "$probe" <<'C'
#include <limits.h>
#include <wchar.h>
#include <stdlib.h>
#if MB_LEN_MAX != 16
#error "FS-001: incorrect target MB_LEN_MAX"
#endif
int fs001_limits_probe(void) { return MB_LEN_MAX; }
C
"$DISTRO_TOOLS_DIR/bin/$DISTRO_TARGET-gcc" --sysroot="$DISTRO_ROOT_DIR" \
  -O2 -D_FORTIFY_SOURCE=2 -c "$probe" -o "$object"
[[ -s "$object" ]] || { echo 'FS-001 target limits compile did not produce an object' >&2; exit 1; }
