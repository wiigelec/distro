#!/usr/bin/env bash
set -euo pipefail

# Stage 0 prototype: foreign-built cross toolchain -> glibc + bash + coreutils
#
# Persistent layout:
#   ~/distro-proto/sources
#   ~/distro-proto/build
#   ~/distro-proto/tools
#   ~/distro-proto/chroot
#   ~/distro-proto/stamps
#
# Run:
#   ./build-stage0.sh
#
# Test:
#   sudo chroot ~/distro-proto/chroot
#   ls

INNER=false
[[ "${1:-}" == "--inner" ]] && INNER=true

if $INNER; then
    # Bubblewrap mount points. Do NOT derive these from HOME: HOME=/tmp inside.
    SOURCES=/sources
    BUILD=/build
    TOOLS=/tools
    CHROOT=/target
    STAMPS=/stamps
    LOGS=/logs
else
    PROTO="${HOME}/distro-proto"
    SOURCES="${PROTO}/sources"
    BUILD="${PROTO}/build"
    TOOLS="${PROTO}/tools"
    CHROOT="${PROTO}/chroot"
    STAMPS="${PROTO}/stamps"
    LOGS="${PROTO}/logs"
fi

JOBS="${JOBS:-$(nproc)}"

BINUTILS_VER=2.47
GCC_VER=16.2.0
GMP_VER=6.3.0
MPFR_VER=4.2.2
MPC_VER=1.4.1
LINUX_VER=7.1.8
GLIBC_VER=2.44
GLIBC_PATCH="glibc-2.44-upstream_fixes-1.patch"
BASH_VER=5.3
COREUTILS_VER=9.11

TGT=x86_64-distro-linux-gnu
STEPS=(binutils gcc linux-headers glibc bash coreutils)

die() { echo "ERROR: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing host command: $1"; }

step_done() {
    local step="$1"
    [[ -f "${STAMPS}/${step}.done" ]] || return 1

    # Do not trust a stamp unless the expected installed artifact exists.
    # This also repairs bad v5 stamps that were written after failed commands.
    case "$step" in
        binutils)
            [[ -x /tools/bin/${TGT}-ld && -x /tools/bin/${TGT}-as ]]
            ;;
        gcc)
            [[ -x /tools/bin/${TGT}-gcc ]]
            ;;
        linux-headers)
            [[ -f /target/usr/include/linux/version.h ]]
            ;;
        glibc)
            [[ -e /target/usr/lib/libc.so.6 && -e /target/usr/lib/libc.so ]]
            ;;
        bash)
            [[ -x /target/usr/bin/bash ]]
            ;;
        coreutils)
            [[ -x /target/usr/bin/ls ]]
            ;;
        *)
            return 1
            ;;
    esac
}

mark_done() {
    local step="$1"
    mkdir -p "$STAMPS"
    {
        echo "step=$step"
        echo "target=$TGT"
        echo "completed_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "${STAMPS}/${step}.done"
}

run_step() {
    local step="$1"
    local fn="$2"
    local log="${LOGS}/${step}.log"

    if step_done "$step"; then
        echo "==> SKIP: $step"
        return 0
    fi

    # Remove stale/bad stamp before attempting the step.
    rm -f "${STAMPS}/${step}.done"
    mkdir -p "$LOGS"

    echo
    echo "============================================================"
    echo "==> BUILD: $step   (-j${JOBS})"
    echo "==> LOG:   $log"
    echo "============================================================"

    : > "$log"

    # Keep the build itself under strict errexit while allowing the parent
    # shell to capture the exit status and print diagnostics.
    set +e
    (
        set -euo pipefail
        "$fn"
    ) 2>&1 | tee "$log"
    local rc=${PIPESTATUS[0]}
    set -e

    if (( rc != 0 )); then
        echo
        echo "============================================================"
        echo "==> FAILED: $step (exit $rc)"
        echo "==> LOG:    $log"
        echo "============================================================"
        echo
        echo "Likely error lines:"
        grep -nEi \
            'error:|fatal:|undefined reference|no such file|cannot |failed|killed|segmentation fault|Error [0-9]+' \
            "$log" | tail -100 || true
        echo
        echo "Last 80 log lines:"
        tail -80 "$log" || true
        return "$rc"
    fi

    mark_done "$step"
    echo "==> DONE: $step"
}

download() {
    local source_name="$1"
    local url="$2"
    local file="${SOURCES}/${url##*/}"

    echo
    echo "============================================================"
    echo "==> SOURCE: $source_name"
    echo "==> URL:    $url"
    echo "==> FILE:   $file"
    if [[ -f "$file" ]]; then
        echo "==> STATUS: cached"
        echo "============================================================"
        return 0
    fi
    echo "==> STATUS: downloading"
    echo "============================================================"

    curl --fail --location --retry 3 -o "$file" "$url"
}

extract() {
    rm -rf "$2"
    mkdir -p "$2"
    tar -xf "/sources/$1" --strip-components=1 -C "$2"
}

status() {
    mkdir -p "$STAMPS"
    local s
    for s in "${STEPS[@]}"; do
        if step_done "$s"; then
            printf "%-16s done\n" "$s"
        else
            printf "%-16s pending\n" "$s"
        fi
    done
}

prepare_sources() {
    mkdir -p "$SOURCES"
    download "binutils ${BINUTILS_VER}" \
        "https://ftpmirror.gnu.org/binutils/binutils-${BINUTILS_VER}.tar.xz"
    download "gcc ${GCC_VER}" \
        "https://ftpmirror.gnu.org/gcc/gcc-${GCC_VER}/gcc-${GCC_VER}.tar.xz"
    download "gmp ${GMP_VER}" \
        "https://ftpmirror.gnu.org/gmp/gmp-${GMP_VER}.tar.xz"
    download "mpfr ${MPFR_VER}" \
        "https://ftpmirror.gnu.org/mpfr/mpfr-${MPFR_VER}.tar.xz"
    download "mpc ${MPC_VER}" \
        "https://ftpmirror.gnu.org/mpc/mpc-${MPC_VER}.tar.xz"
    download "linux ${LINUX_VER}" \
        "https://cdn.kernel.org/pub/linux/kernel/v7.x/linux-${LINUX_VER}.tar.xz"
    download "glibc ${GLIBC_VER}" \
        "https://ftpmirror.gnu.org/glibc/glibc-${GLIBC_VER}.tar.xz"
    download "glibc upstream fixes patch" \
        "https://www.linuxfromscratch.org/patches/downloads/glibc/${GLIBC_PATCH}"
    download "bash ${BASH_VER}" \
        "https://ftpmirror.gnu.org/bash/bash-${BASH_VER}.tar.gz"
    download "coreutils ${COREUTILS_VER}" \
        "https://ftpmirror.gnu.org/coreutils/coreutils-${COREUTILS_VER}.tar.xz"
}

init_target() {
    mkdir -p \
        /target/etc /target/root /target/var \
        /target/usr/bin /target/usr/lib /target/usr/sbin \
        /target/usr/include /target/usr/share /target/lib64
    ln -sfn usr/bin /target/bin
    ln -sfn usr/lib /target/lib
    ln -sfn usr/sbin /target/sbin
}

build_binutils() {
    extract "binutils-${BINUTILS_VER}.tar.xz" /build/binutils-src
    rm -rf /build/binutils-build
    mkdir /build/binutils-build
    cd /build/binutils-build

    /build/binutils-src/configure \
        --prefix=/tools \
        --with-sysroot=/target \
        --target="$TGT" \
        --disable-nls \
        --enable-gprofng=no \
        --disable-werror \
        --enable-new-dtags \
        --enable-default-hash-style=gnu

    make -j"$JOBS"
    make -j"$JOBS" install
    test -x "/tools/bin/${TGT}-ld"
    test -x "/tools/bin/${TGT}-as"
}

build_gcc() {
    extract "gcc-${GCC_VER}.tar.xz" /build/gcc-src

    tar -xf "/sources/gmp-${GMP_VER}.tar.xz" -C /build/gcc-src
    mv "/build/gcc-src/gmp-${GMP_VER}" /build/gcc-src/gmp
    tar -xf "/sources/mpfr-${MPFR_VER}.tar.xz" -C /build/gcc-src
    mv "/build/gcc-src/mpfr-${MPFR_VER}" /build/gcc-src/mpfr
    tar -xf "/sources/mpc-${MPC_VER}.tar.xz" -C /build/gcc-src
    mv "/build/gcc-src/mpc-${MPC_VER}" /build/gcc-src/mpc

    sed -e '/m64=/s/lib64/lib/' -i /build/gcc-src/gcc/config/i386/t-linux64

    rm -rf /build/gcc-build
    mkdir /build/gcc-build
    cd /build/gcc-build

    /build/gcc-src/configure \
        --target="$TGT" \
        --prefix=/tools \
        --with-glibc-version="$GLIBC_VER" \
        --with-sysroot=/target \
        --with-newlib \
        --without-headers \
        --enable-default-pie \
        --enable-default-ssp \
        --disable-fixincludes \
        --disable-nls \
        --disable-shared \
        --disable-multilib \
        --disable-threads \
        --disable-libatomic \
        --disable-libgomp \
        --disable-libquadmath \
        --disable-libssp \
        --disable-libvtv \
        --disable-libstdcxx \
        --enable-languages=c

    make -j"$JOBS"
    make -j"$JOBS" install

    cat \
        /build/gcc-src/gcc/limitx.h \
        /build/gcc-src/gcc/glimits.h \
        /build/gcc-src/gcc/limity.h \
        > "$("$TGT-gcc" -print-file-name=include)/limits.h"

    test -x "/tools/bin/${TGT}-gcc"
}

build_linux_headers() {
    extract "linux-${LINUX_VER}.tar.xz" /build/linux-src
    cd /build/linux-src
    make mrproper
    make -j"$JOBS" headers
    find usr/include -type f ! -name '*.h' -delete
    rm -rf /target/usr/include
    cp -rv usr/include /target/usr/
    test -f /target/usr/include/linux/version.h
}

build_glibc() {
    extract "glibc-${GLIBC_VER}.tar.xz" /build/glibc-src

    cd /build/glibc-src
    patch -Np1 -i "/sources/${GLIBC_PATCH}"

    ln -sfn ../lib/ld-linux-x86-64.so.2 \
        /target/lib64/ld-linux-x86-64.so.2

    rm -rf /build/glibc-build
    mkdir /build/glibc-build
    cd /build/glibc-build

    cat > configparms <<'EOF'
rootsbindir=/usr/sbin

# Stage 0 deliberately has no target C++ runtime yet.  The foreign host may
# have g++, but allowing Glibc to detect/use it makes support/links-dso-program
# select the C++ implementation and link against host/target libstdc++.
# Force Glibc's support build onto its C-only bootstrap path.
CXX =
EOF

    CXX= \
    /build/glibc-src/configure \
        --prefix=/usr \
        --host="$TGT" \
        --build="$(cd /build/glibc-src && ./scripts/config.guess)" \
        --disable-nscd \
        libc_cv_slibdir=/usr/lib \
        --enable-kernel=5.10

    make -j"$JOBS"
    make -j"$JOBS" DESTDIR=/target install

    if [[ -f /target/usr/bin/ldd ]]; then
        sed '/RTLDLIST=/s@/usr@@g' -i /target/usr/bin/ldd
    fi

    test -e /target/usr/lib/libc.so.6

    cd /build
    printf 'int main(void){return 0;}\n' | "$TGT-gcc" -x c - -o sanity
    "$TGT-readelf" -l sanity | grep 'Requesting program interpreter'
    rm -f sanity
}

build_bash() {
    extract "bash-${BASH_VER}.tar.gz" /build/bash-src
    rm -rf /build/bash-build
    mkdir /build/bash-build
    cd /build/bash-build

    /build/bash-src/configure \
        --prefix=/usr \
        --build="$(cd /build/bash-src && sh support/config.guess)" \
        --host="$TGT" \
        --without-bash-malloc \
        --disable-readline \
        --disable-nls

    make -j"$JOBS"
    make -j"$JOBS" DESTDIR=/target install

    ln -sfn bash /target/usr/bin/sh

    test -x /target/usr/bin/bash
    "$TGT-readelf" -l /target/usr/bin/bash |
        grep 'Requesting program interpreter'

    ! "$TGT-readelf" -d /target/usr/bin/bash |
        grep -qE 'RPATH|RUNPATH' ||
        die "bash contains RPATH/RUNPATH"
}

build_coreutils() {
    extract "coreutils-${COREUTILS_VER}.tar.xz" /build/coreutils-src
    rm -rf /build/coreutils-build
    mkdir /build/coreutils-build
    cd /build/coreutils-build

    /build/coreutils-src/configure \
        --prefix=/usr \
        --host="$TGT" \
        --build="$(cd /build/coreutils-src && ./build-aux/config.guess)" \
        --disable-nls

    make -j"$JOBS"
    make -j"$JOBS" DESTDIR=/target install

    test -x /target/usr/bin/ls
    "$TGT-readelf" -l /target/usr/bin/ls |
        grep 'Requesting program interpreter'

    ! "$TGT-readelf" -d /target/usr/bin/ls |
        grep -qE 'RPATH|RUNPATH' ||
        die "ls contains RPATH/RUNPATH"
}

finalize_target() {
    cat > /target/etc/passwd <<'EOF'
root:x:0:0:root:/root:/bin/bash
EOF
    cat > /target/etc/group <<'EOF'
root:x:0:
EOF

    test -x /target/usr/bin/bash
    test -x /target/usr/bin/ls
    test -e /target/usr/lib/libc.so.6

    echo
    echo "==> Stage 0 ready"
    echo "bash dependencies:"
    "$TGT-readelf" -d /target/usr/bin/bash | grep NEEDED || true
    echo "ls dependencies:"
    "$TGT-readelf" -d /target/usr/bin/ls | grep NEEDED || true
}

inner() {
    export PATH=/tools/bin:/usr/bin:/bin
    export LC_ALL=C LANG=C
    unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH LD_LIBRARY_PATH \
          PKG_CONFIG_PATH PKG_CONFIG_LIBDIR CMAKE_PREFIX_PATH CONFIG_SITE || true

    init_target

    run_step binutils      build_binutils
    run_step gcc           build_gcc
    run_step linux-headers build_linux_headers
    run_step glibc         build_glibc
    run_step bash          build_bash
    run_step coreutils     build_coreutils

    finalize_target
}

outer() {
    [[ "$(uname -m)" == x86_64 ]] || die "prototype currently supports x86_64 only"

    for c in bwrap curl gcc g++ make tar xz gzip sed awk grep patch perl python3 nproc; do
        need "$c"
    done

    mkdir -p "$SOURCES" "$BUILD" "$TOOLS" "$CHROOT" "$STAMPS" "$LOGS"

    case "${1:-}" in
        --status)
            status
            exit
            ;;
        --clean-from)
            [[ $# -eq 2 ]] || die "usage: $0 --clean-from <step>"
            local wanted="$2"
            local found=false
            local s
            for s in "${STEPS[@]}"; do
                if [[ "$s" == "$wanted" ]]; then
                    found=true
                fi
                if $found; then
                    echo "==> invalidating $s"
                    rm -f "${STAMPS}/${s}.done"
                fi
            done
            $found || die "unknown step: $wanted"
            exit
            ;;
        --clean-all)
            rm -rf "$BUILD" "$TOOLS" "$CHROOT" "$STAMPS" "$LOGS"
            mkdir -p "$BUILD" "$TOOLS" "$CHROOT" "$STAMPS" "$LOGS"
            exit
            ;;
        "")
            ;;
        *)
            die "usage: $0 [--status|--clean-from <step>|--clean-all]"
            ;;
    esac

    prepare_sources

    local self
    self="$(readlink -f "$0")"

    local -a b=(
        --unshare-user-try
        --unshare-pid
        --unshare-ipc
        --unshare-uts
        --unshare-net
        --die-with-parent
        --clearenv

        --ro-bind /usr /usr
        --ro-bind /etc /etc
        --ro-bind "$SOURCES" /sources
        --bind "$BUILD" /build
        --bind "$TOOLS" /tools
        --bind "$CHROOT" /target
        --bind "$STAMPS" /stamps
        --bind "$LOGS" /logs
        --ro-bind "$self" /driver.sh

        --proc /proc
        --dev /dev
        --tmpfs /tmp

        --setenv HOME /tmp
        --setenv USER builder
        --setenv LOGNAME builder
        --setenv LC_ALL C
        --setenv LANG C
        --setenv PATH /tools/bin:/usr/bin:/bin
        --setenv JOBS "$JOBS"

        --chdir /build
    )

    local d
    for d in /bin /sbin /lib /lib64; do
        [[ -e "$d" ]] && b+=(--ro-bind "$d" "$d")
    done

    echo "==> jobs: $JOBS ($(nproc) CPUs detected)"
    bwrap "${b[@]}" /bin/bash /driver.sh --inner

    echo
    echo "Test with:"
    echo "  sudo chroot ~/distro-proto/chroot"
    echo "  ls"
}

if $INNER; then
    inner
else
    outer "$@"
fi
