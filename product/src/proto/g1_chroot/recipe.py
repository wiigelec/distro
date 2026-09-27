#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "distro-g1-chroot-prototype/1"

METHODS = (
    ("autotools", ("configure",)),
    ("cmake", ("CMakeLists.txt",)),
    ("meson", ("meson.build",)),
    ("cargo", ("Cargo.toml",)),
    ("python", ("pyproject.toml", "setup.py")),
)

DOCUMENTATION = (
    "INSTALL",
    "INSTALL.md",
    "README",
    "README.md",
    "README.txt",
    "doc/INSTALL",
    "doc/README",
    "docs/INSTALL",
    "docs/README",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(
    url: str,
    destination: Path,
    *,
    attempts: int = 4,
    timeout: int = 120,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, attempts + 1):
        try:
            temporary.unlink(missing_ok=True)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                with temporary.open("wb") as output:
                    shutil.copyfileobj(response, output)
            temporary.replace(destination)
            return
        except (OSError, urllib.error.URLError) as error:
            temporary.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            delay = 2 ** (attempt - 1)
            print(
                f"==> fetch retry {attempt}/{attempts - 1} "
                f"after {error}; sleeping {delay}s",
                flush=True,
            )
            time.sleep(delay)


def safe_extract(archive: Path, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    resolved_root = destination.resolve()
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if target != resolved_root and resolved_root not in target.parents:
                raise RuntimeError(
                    f"source archive member escapes extraction root: {member.name}"
                )
        tar.extractall(destination, filter="data")

    children = list(destination.iterdir())
    top_dirs = [path for path in children if path.is_dir()]
    if len(children) != 1 or len(top_dirs) != 1:
        raise RuntimeError(
            f"{archive.name}: expected exactly one top-level source directory"
        )
    return top_dirs[0]


def detect_method(source: Path) -> tuple[str, list[str]]:
    evidence = []
    for method, markers in METHODS:
        present = [marker for marker in markers if (source / marker).is_file()]
        if present:
            evidence.extend(present)
            return method, evidence
    raise RuntimeError(f"{source}: unable to identify supported build system")


def documentation_evidence(source: Path) -> list[str]:
    return [name for name in DOCUMENTATION if (source / name).is_file()]


def commands_for(package: str, method: str) -> list[str]:
    if method == "linux-kernel":
        return [
            'cd "$SRC" && make O="$BUILD" x86_64_defconfig',
            (
                'cd "$SRC" && scripts/config --file "$BUILD/.config"'
                " -d MODULES"
                " -d SYSTEM_TRUSTED_KEYRING"
                " -d SYSTEM_REVOCATION_LIST"
                " -d CFG80211"
                " -e BLK_DEV"
                " -e PCI"
                " -e VIRTIO"
                " -e VIRTIO_PCI"
                " -e VIRTIO_BLK"
                " -e EXT4_FS"
                " -e DEVTMPFS"
                " -e DEVTMPFS_MOUNT"
                " -e TMPFS"
                " -e CGROUPS"
                " -e VT"
                " -e VT_CONSOLE"
            ),
            'cd "$SRC" && make O="$BUILD" olddefconfig',
            'cd "$SRC" && make O="$BUILD" -j"$JOBS"',
            'cd "$SRC" && make -j"$JOBS" headers_install INSTALL_HDR_PATH="$DESTDIR/usr"',
            'release="$(cd "$SRC" && make -s O="$BUILD" kernelrelease)" && install -Dm755 "$BUILD/arch/x86/boot/bzImage" "$DESTDIR/boot/vmlinuz-$release"',
        ]
    if method == "ninja-bootstrap":
        # Ninja's upstream bootstrap path needs only Python and a C++ compiler,
        # both already present in the completed G1 chroot.
        return [
            'cd "$SRC" && python3 configure.py --bootstrap',
            'install -Dm755 "$SRC/ninja" "$DESTDIR/usr/bin/ninja"',
        ]
    if method == "python-binascii":
        # Add only the stdlib extension Meson needs. Build it against the
        # already-installed G1 Python and omit optional zlib acceleration.
        return [
            (
                'src_version="$(awk \'/^#define PY_MAJOR_VERSION / {major=$3} '
                '/^#define PY_MINOR_VERSION / {minor=$3} '
                'END {print major "." minor}\' "$SRC/Include/patchlevel.h")"'
                ' && runtime_version="$(python3 -c \'import sys; '
                'print(f"{sys.version_info.major}.{sys.version_info.minor}")\')"'
                ' && test "$src_version" = "$runtime_version"'
            ),
            (
                'include="$(python3 -c \'import sysconfig; '
                'print(sysconfig.get_path("include"))\')"'
                ' && suffix="$(python3 -c \'import sysconfig; '
                'print(sysconfig.get_config_var("EXT_SUFFIX"))\')"'
                ' && cc="$(python3 -c \'import sysconfig; '
                'print(sysconfig.get_config_var("CC").split()[0])\')"'
                ' && "$cc" -shared -fPIC $(python3-config --cflags)'
                ' -I"$include/internal" "$SRC/Modules/binascii.c"'
                ' -o "$BUILD/binascii$suffix"'
            ),
            (
                'stdlib="$(python3 -c \'import sysconfig; '
                'print(sysconfig.get_path("stdlib"))\')"'
                ' && suffix="$(python3 -c \'import sysconfig; '
                'print(sysconfig.get_config_var("EXT_SUFFIX"))\')"'
                ' && install -Dm755 "$BUILD/binascii$suffix"'
                ' "$DESTDIR$stdlib/lib-dynload/binascii$suffix"'
            ),
        ]
    if method == "python-zlib":
        # Build Python's zlib extension against the zlib package installed
        # in the G1 root. Keep the extension ABI-matched to the runtime.
        return [
            (
                'src_version="$(awk \'/^#define PY_MAJOR_VERSION / {major=$3} '
                '/^#define PY_MINOR_VERSION / {minor=$3} '
                'END {print major "." minor}\' "$SRC/Include/patchlevel.h")"'
                ' && runtime_version="$(python3 -c \'import sys; '
                'print(f"{sys.version_info.major}.{sys.version_info.minor}")\')"'
                ' && test "$src_version" = "$runtime_version"'
            ),
            (
                'include="$(python3 -c \'import sysconfig; '
                'print(sysconfig.get_path("include"))\')"'
                ' && suffix="$(python3 -c \'import sysconfig; '
                'print(sysconfig.get_config_var("EXT_SUFFIX"))\')"'
                ' && cc="$(python3 -c \'import sysconfig; '
                'print(sysconfig.get_config_var("CC").split()[0])\')"'
                ' && "$cc" -shared -fPIC $(python3-config --cflags)'
                ' -I"$include/internal" "$SRC/Modules/zlibmodule.c"'
                ' -L/usr/lib64 -Wl,-rpath-link,/usr/lib64 -lz'
                ' -o "$BUILD/zlib$suffix"'
            ),
            (
                'stdlib="$(python3 -c \'import sysconfig; '
                'print(sysconfig.get_path("stdlib"))\')"'
                ' && suffix="$(python3 -c \'import sysconfig; '
                'print(sysconfig.get_config_var("EXT_SUFFIX"))\')"'
                ' && install -Dm755 "$BUILD/zlib$suffix"'
                ' "$DESTDIR$stdlib/lib-dynload/zlib$suffix"'
            ),
        ]
    if method == "perl":
        # Perl is a build-time dependency for libxcrypt. Use upstream's
        # native Configure flow and stage installation with DESTDIR.
        return [
            'cd "$SRC" && sh Configure -des -Dcc=gcc -Dprefix=/usr -Dman1dir=none -Dman3dir=none',
            'cd "$SRC" && make -j"$JOBS"',
            'cd "$SRC" && make DESTDIR="$DESTDIR" install',
        ]
    if method == "autotools":
        configure = 'cd "$BUILD" && "$SRC/configure" --prefix=/usr'
        if package == "glibc":
            # Keep system administration binaries under the merged-/usr
            # executable path so /sbin can remain a compatibility symlink.
            configure += " --sbindir=/usr/bin"
        elif package == "gmp":
            # GMP 6.3.0's compiler probe is not C23-clean. GCC 15 defaults
            # to gnu23, so force the older GNU C dialect expected by the
            # upstream configure test while leaving GMP's ABI/optimization
            # selection intact.
            configure = (
                'cd "$BUILD" && CC="gcc -std=gnu17" "$SRC/configure"'
                " --prefix=/usr --libdir=/usr/lib64"
            )
        elif package in ("mpfr", "mpc"):
            # Keep bootstrap shared libraries on the loader-visible x86_64
            # runtime path used by the G1 root.
            configure += " --libdir=/usr/lib64"
        elif package == "ncurses":
            # Learned from upstream INSTALL after runtime closure showed Bash
            # linked against libncursesw.so.6 while the default ncurses build
            # staged only static libraries.
            configure += " --with-shared --with-versioned-syms --libdir=/usr/lib64"
        elif package == "binutils":
            # Avoid optional G0 integrations in the bootstrap toolchain.
            configure += (
                " --disable-gprofng"
                " --without-zstd"
                " --without-debuginfod"
            )
        elif package == "make":
            # Guile support is optional and otherwise auto-detects host Guile
            # and its garbage collector.
            configure += " --without-guile"
        elif package == "gcc":
            # Build the native bootstrap compiler without a three-stage GCC
            # bootstrap and without 32-bit multilib requirements.
            configure += (
                " --disable-bootstrap"
                " --disable-multilib"
                " --enable-languages=c,c++"
                " --without-isl"
                " --without-zstd"
            )
        elif package == "gawk":
            # Readline is optional for gawk's interactive debugger. Avoid
            # auto-detecting the G0 library in the bootstrap build.
            configure += " --without-readline"
        elif package == "bison":
            # libtextstyle is optional, but the prefix switch alone still
            # permits system discovery. Force the configure cache result to
            # no so the bootstrap build cannot link a G0 libtextstyle.
            configure = (
                'cd "$BUILD" && ac_cv_libtextstyle=no "$SRC/configure"'
                " --prefix=/usr"
            )
        elif package == "tar":
            # Tar 1.35's own ACL configure knob is --without-posix-acls.
            # That path also disables gnulib ACL probing, preventing the
            # bootstrap archiver from linking the G0 libacl.
            configure += " --without-posix-acls"
        elif package == "python":
            # In an out-of-tree CPython build, configure consumes
            # Modules/Setup.local from the build tree. Disable only extension
            # modules proven by runtime closure to link against G0 libraries.
            configure = (
                'mkdir -p "$BUILD/Modules"'
                ' && printf "%s\\n"'
                ' "*disabled*"'
                ' "_bz2 zlib _uuid _zstd binascii _hashlib _decimal _lzma"'
                ' "_dbm readline _gdbm _ctypes _ssl _sqlite3"'
                ' > "$BUILD/Modules/Setup.local"'
                ' && cd "$BUILD" && "$SRC/configure" --prefix=/usr --with-ensurepip=no'
            )
        elif package == "grep":
            # PCRE2 support is optional and otherwise auto-detects the G0
            # library, introducing an undeclared runtime dependency.
            configure += " --disable-perl-regexp"
        elif package == "rsync":
            # Rsync bundles popt and can operate without these optional
            # host integrations. Keep the bootstrap package self-contained
            # instead of linking against G0-only libraries.
            configure += (
                " --with-included-popt"
                " --disable-acl-support"
                " --disable-xattr-support"
                " --disable-openssl"
                " --disable-xxhash"
                " --disable-zstd"
                " --disable-lz4"
                " --disable-idn"
            )
        elif package == "sed":
            # Sed's ACL/xattr support is optional. Disable host-detected
            # integrations so the bootstrap package does not acquire
            # undeclared libacl/libattr runtime dependencies.
            configure += " --disable-acl --disable-xattr"
        elif package == "coreutils":
            # Keep the bootstrap closure minimal and deterministic. Coreutils
            # otherwise auto-detects optional G0 libraries and links against
            # them, making the staged G1 payload depend on undeclared host
            # capabilities.
            configure += (
                " --disable-xattr"
                " --disable-acl"
                " --disable-libcap"
                " --without-libgmp"
                " --with-openssl=no"
            )
        elif package == "libxcrypt":
            # GCC 16 diagnoses two upstream const-qualification assignments.
            # Keep upstream's warning set while making only that warning
            # non-fatal for this release.
            configure = (
                'cd "$BUILD" && CFLAGS="-O2 -g -Wno-error=discarded-qualifiers" "$SRC/configure"'
                " --prefix=/usr --libdir=/usr/lib64"
            )
        elif package == "shadow":
            # Keep the first console-login proof independent of PAM, audit,
            # SELinux, ACL, libbsd, and logind integrations.
            configure += (
                " --bindir=/usr/bin"
                " --sbindir=/usr/bin"
                " --libdir=/usr/lib64"
                " --without-libpam"
                " --without-audit"
                " --without-selinux"
                " --without-acl"
                " --without-libbsd"
                " --disable-logind"
            )
        elif package == "grub":
            # GRUB 2.12's release archive omitted grub-core/extra_deps.lst.
            # Restore the upstream file before configuring the BIOS-only build.
            configure = (
                'printf "%s\\n" "depends bli part_gpt"'
                ' > "$SRC/grub-core/extra_deps.lst"'
                " && "
                + configure
                + " --sbindir=/usr/bin"
                + " --disable-nls"
                + " --disable-werror"
                + " --with-platform=pc"
            )
        elif package == "zlib":
            # Keep x86_64 shared libraries on G1's loader-visible lib64 path.
            configure += " --libdir=/usr/lib64 --sharedlibdir=/usr/lib64"
        elif package == "pkgconf":
            # pkgconf installs a shared libpkgconf used by its CLI.
            # Keep it on G1's loader-visible x86_64 runtime path.
            configure += " --libdir=/usr/lib64"
        elif package == "elfutils":
            # Linux objtool requires libelf development headers, including
            # gelf.h. Keep this G1 build-tool package focused on the core
            # libelf surface and avoid unrelated compression, localization,
            # archive, and debuginfod dependency chains.
            configure += (
                " --libdir=/usr/lib64"
                " --disable-nls"
                " --disable-debuginfod"
                " --disable-libdebuginfod"
                " --without-bzlib"
                " --without-lzma"
                " --without-zstd"
                " --without-libarchive"
            )
        if package == "bc":
            # The kernel build only needs the bc calculator. Build and stage
            # the executable directly so bootstrap does not require Texinfo
            # solely to regenerate upstream documentation.
            return [
                configure,
                'cd "$BUILD" && make -C lib -j"$JOBS" && make -C bc -j"$JOBS"',
                'install -Dm755 "$BUILD/bc/bc" "$DESTDIR/usr/bin/bc"',
            ]
        if package == "pkgconf":
            return [
                configure,
                'cd "$BUILD" && make -j"$JOBS"',
                (
                    'cd "$BUILD" && make DESTDIR="$DESTDIR" install'
                    ' && ln -sf pkgconf "$DESTDIR/usr/bin/pkg-config"'
                ),
            ]
        if package == "binutils":
            # arlex.l provides yywrap itself, so the Flex runtime library
            # detected by configure is unnecessary. Override LEXLIB only for
            # Binutils to avoid a libfl runtime dependency in ar and ranlib.
            return [
                configure,
                'cd "$BUILD" && make -j"$JOBS" LEXLIB=',
                'cd "$BUILD" && make DESTDIR="$DESTDIR" LEXLIB= install',
            ]
        return [
            configure,
            'cd "$BUILD" && make -j"$JOBS"',
            'cd "$BUILD" && make DESTDIR="$DESTDIR" install',
        ]
    if method == "cmake":
        return [
            'cmake -S "$SRC" -B "$BUILD" -DCMAKE_INSTALL_PREFIX=/usr',
            'cmake --build "$BUILD" --parallel "$JOBS"',
            'DESTDIR="$DESTDIR" cmake --install "$BUILD"',
        ]
    if method == "meson":
        if package == "util-linux":
            # Retain only the tools needed for the first boot/login proof and
            # avoid host-detected optional integrations.
            return [
                (
                    'meson setup "$BUILD" "$SRC" --prefix=/usr --sbindir=bin'
                    " -Dbuild-python=disabled"
                    " -Dselinux=disabled"
                    " -Daudit=disabled"
                    " -Dsystemd=disabled"
                    " -Dcryptsetup=disabled"
                    " -Dcryptsetup-dlopen=disabled"
                    " -Dzlib=disabled"
                    " -Dlibpcre2-posix=disabled"
                    " -Dmagic=disabled"
                    " -Deconf=disabled"
                    " -Dbuild-login=disabled"
                    " -Dbuild-su=disabled"
                    " -Dbuild-runuser=disabled"
                    " -Dbuild-chfn-chsh=disabled"
                    " -Dbuild-newgrp=disabled"
                    " -Dbuild-nologin=disabled"
                    " -Dbuild-agetty=enabled"
                    " -Dbuild-mount=enabled"
                    " -Dprogram-tests=false"
                ),
                'meson compile -C "$BUILD" -j "$JOBS"',
                'DESTDIR="$DESTDIR" meson install -C "$BUILD"',
            ]
        if package == "systemd":
            # Build only the local init/service-manager surface needed to
            # reach a console login. Networking, initrd, PAM, security
            # integrations, and optional compression/crypto stacks are out of
            # scope for this milestone.
            return [
                (
                    'meson setup "$BUILD" "$SRC" --prefix=/usr --sbindir=bin --libdir=lib64'
                    " -Dmode=release"
                    " -Dsplit-bin=false"
                    " -Defi=false"
                    " -Dbootloader=disabled"
                    " -Dukify=disabled"
                    " -Dinitrd=false"
                    " -Dhibernate=false"
                    " -Dnetworkd=false"
                    " -Dresolve=false"
                    " -Dtimesyncd=false"
                    " -Dremote=disabled"
                    " -Dcoredump=false"
                    " -Dpstore=false"
                    " -Doomd=false"
                    " -Dlogind=false"
                    " -Dhostnamed=false"
                    " -Dlocaled=false"
                    " -Dtimedated=false"
                    " -Dmachined=false"
                    " -Dportabled=false"
                    " -Dhomed=disabled"
                    " -Dnspawn=disabled"
                    " -Dvmspawn=disabled"
                    " -Drepart=disabled"
                    " -Dsysupdate=disabled"
                    " -Dimportd=disabled"
                    " -Dseccomp=disabled"
                    " -Dselinux=disabled"
                    " -Dapparmor=disabled"
                    " -Dpolkit=disabled"
                    " -Dacl=disabled"
                    " -Daudit=disabled"
                    " -Dblkid=disabled"
                    " -Dfdisk=disabled"
                    " -Dkmod=disabled"
                    " -Dpam=disabled"
                    " -Dlibcryptsetup=disabled"
                    " -Dlibcurl=disabled"
                    " -Dlibidn2=disabled"
                    " -Dqrencode=disabled"
                    " -Dgnutls=disabled"
                    " -Dopenssl=disabled"
                    " -Dtpm2=disabled"
                    " -Dzlib=disabled"
                    " -Dbzip2=disabled"
                    " -Dlz4=disabled"
                    " -Dzstd=disabled"
                    " -Dpcre2=disabled"
                    " -Dtranslations=false"
                    " -Dman=disabled"
                    " -Dhtml=disabled"
                ),
                'meson compile -C "$BUILD" -j "$JOBS"',
                'DESTDIR="$DESTDIR" meson install -C "$BUILD"',
            ]
        return [
            'meson setup "$BUILD" "$SRC" --prefix=/usr',
            'meson compile -C "$BUILD" -j "$JOBS"',
            'DESTDIR="$DESTDIR" meson install -C "$BUILD"',
        ]
    if method == "cargo":
        return [
            'cd "$SRC" && cargo build --release',
            'echo "cargo install staging requires recipe refinement" >&2; exit 2',
        ]
    if method == "python":
        if package in ("markupsafe", "jinja2"):
            # These are Python build-time modules for systemd. Install the
            # source packages directly into G1's site-packages rather than
            # introducing pip/flit/setuptools into the bootstrap environment.
            # MarkupSafe falls back to its pure-Python implementation when its
            # optional C speedup module is absent.
            module = "markupsafe" if package == "markupsafe" else "jinja2"
            return [
                (
                    'site="$(python3 -c \'import sysconfig; '
                    'print(sysconfig.get_path("purelib"))\')"'
                    ' && install -d "$DESTDIR$site"'
                    ' && cp -a "$SRC/src/' + module + '" "$DESTDIR$site/"'
                ),
            ]
        if package == "meson":
            # Meson is pure Python. Install its source package directly and
            # avoid Python's zipapp/zipfile path, which depends on stdlib
            # extensions intentionally omitted from the accepted G1 Python.
            return [
                'install -d "$DESTDIR/usr/bin" "$DESTDIR/usr/lib/meson"',
                'cp "$SRC/meson.py" "$DESTDIR/usr/lib/meson/meson.py"',
                'cp -a "$SRC/mesonbuild" "$DESTDIR/usr/lib/meson/mesonbuild"',
                (
                    'printf "%s\\n" "#!/bin/sh"'
                    ' "exec python3 /usr/lib/meson/meson.py \"\\$@\""'
                    ' > "$DESTDIR/usr/bin/meson"'
                ),
                'chmod 0755 "$DESTDIR/usr/bin/meson"',
            ]
        return [
            'cd "$SRC" && python -m build',
            'echo "python install staging requires recipe refinement" >&2; exit 2',
        ]
    raise RuntimeError(f"unsupported build method: {method}")


def derive_recipe(
    resolved: dict,
    output_root: Path,
    *,
    seed_output: Path | None = None,
) -> dict:
    package = resolved["name"]
    version = resolved["version"]
    source_url = resolved["source_url"]

    parsed = urllib.parse.urlparse(source_url)
    filename = Path(parsed.path).name
    if not filename:
        raise RuntimeError(f"{package}: source URL has no archive filename")

    archive = output_root / "sources" / filename
    archive.parent.mkdir(parents=True, exist_ok=True)
    expected_checksum = resolved.get("source_sha256")
    have_source = False

    if archive.is_file():
        checksum = sha256_file(archive)
        if expected_checksum is None or checksum == expected_checksum:
            print(f"==> {package}: reuse output source {archive}", flush=True)
            have_source = True
        else:
            print(
                f"==> {package}: discard output source with checksum mismatch",
                flush=True,
            )
            archive.unlink()

    if not have_source and seed_output is not None:
        seed_archive = seed_output / "sources" / filename
        if seed_archive.is_file():
            seed_checksum = sha256_file(seed_archive)
            if expected_checksum is None or seed_checksum == expected_checksum:
                print(
                    f"==> {package}: reuse seed source {seed_archive}",
                    flush=True,
                )
                shutil.copy2(seed_archive, archive)
                have_source = True
            else:
                print(
                    f"==> {package}: seed source checksum mismatch; fetch fallback",
                    flush=True,
                )

    if not have_source:
        print(f"==> {package}: fetch {source_url}", flush=True)
        download(source_url, archive)

    checksum = sha256_file(archive)
    if expected_checksum is not None and checksum != expected_checksum:
        raise RuntimeError(
            f"{package}: source checksum mismatch: "
            f"expected {expected_checksum}, got {checksum}"
        )

    extract_root = output_root / "work" / f"{package}-{version}" / "unpack"
    source = safe_extract(archive, extract_root)

    if (
        package == "linux"
        and (source / "Makefile").is_file()
        and (source / "include/uapi/linux").is_dir()
    ):
        method = "linux-kernel"
        markers = ["Makefile", "include/uapi/linux"]
    elif package == "ninja" and (source / "configure.py").is_file():
        method = "ninja-bootstrap"
        markers = ["configure.py"]
    elif package == "python-binascii" and (source / "Modules/binascii.c").is_file():
        method = "python-binascii"
        markers = ["Modules/binascii.c", "Include/patchlevel.h"]
    elif package == "python-zlib" and (source / "Modules/zlibmodule.c").is_file():
        method = "python-zlib"
        markers = ["Modules/zlibmodule.c", "Include/patchlevel.h"]
    elif package == "perl" and (source / "Configure").is_file() and (source / "perl.c").is_file():
        method = "perl"
        markers = ["Configure", "perl.c"]
    else:
        method, markers = detect_method(source)
    docs = documentation_evidence(source)

    recipe = {
        "schema_version": 1,
        "candidate": True,
        "identity": {
            "name": package,
            "version": version,
            "architecture": "x86_64",
            "revision": "r1",
        },
        "source": {
            "url": source_url,
            "sha256": checksum,
        },
        "discovery": {
            "management": resolved["management"],
            "discovery_url": resolved["discovery_url"],
            "build_method": method,
            "method_evidence": markers,
            "documentation_evidence": docs,
        },
        "build": {
            "system": method,
            "commands": commands_for(package, method),
        },
    }

    recipe_dir = output_root / "recipes"
    recipe_dir.mkdir(parents=True, exist_ok=True)
    recipe_path = recipe_dir / f"{package}.json"
    recipe_path.write_text(
        json.dumps(recipe, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return {
        "name": package,
        "version": version,
        "source_url": source_url,
        "source_sha256": checksum,
        "build_system": method,
        "method_evidence": markers,
        "documentation_evidence": docs,
        "recipe": str(recipe_path),
    }
