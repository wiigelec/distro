"""Functional checks for a constructed cross-toolchain, inside its build sandbox."""
from __future__ import annotations
import os
from pathlib import Path
import re
import subprocess
from build.host_sandbox import _base_command, _workspace_mounts, SandboxError


class CrossToolchainVerificationError(RuntimeError):
    """The constructed compiler, linker or target runtime failed verification."""


# C/C++ binaries are linked but not run: they belong to the target system.
# The sandbox mounts the build tree at /work and target sysroot at /toolchain.
CHECK_SCRIPT = r'''set -euo pipefail
TARGET="$1"
if [[ -n "${DISTRO_ORIGINAL_HOST_PATH:-}" && -e "$DISTRO_ORIGINAL_HOST_PATH" ]]; then
    echo "original workspace unexpectedly accessible" >&2; exit 1
fi
TOOLS="/toolchain/tools/bin"
SYSROOT="/toolchain"
for tool in gcc g++ ld readelf; do
    test -x "$TOOLS/$TARGET-$tool" || { echo "missing target tool: $tool" >&2; exit 1; }
done
for tool in gcc g++; do
    test "$("$TOOLS/$TARGET-$tool" -dumpmachine)" = "$TARGET" || {
        echo "incorrect compiler target: $tool" >&2; exit 1;
    }
    test "$("$TOOLS/$TARGET-$tool" -print-sysroot)" = "$SYSROOT" || {
        echo "incorrect compiler sysroot: $tool" >&2; exit 1;
    }
done
# Inspect actual preprocessor dependencies, not GCC's preferred textual
# representation of a search directory or startup-object filename.
for language in c c++; do
    if [[ "$language" = c ]]; then
        driver="$TOOLS/$TARGET-gcc"
        header=stdio.h
    else
        driver="$TOOLS/$TARGET-g++"
        header=iostream
    fi
    dependencies="$(printf '#include <%s>\n' "$header" | "$driver" -x "$language" -M -)"
    printf '%s\n' "$dependencies" | grep -Fq '/toolchain/' || {
        echo "target headers not resolved beneath sysroot: $language" >&2; exit 1;
    }
    if printf '%s\n' "$dependencies" | grep -Eq '(^|[[:space:]])/(usr|lib|lib64)/'; then
        echo "host header fallback detected: $language" >&2; exit 1
    fi
done
# The following actual C/C++ links exercise the startup objects and target
# linker resolution without assuming GCC prints absolute -print-file-name paths.
"$TOOLS/$TARGET-ld" --version >/dev/null
"$TOOLS/$TARGET-readelf" --version >/dev/null
test -d "$SYSROOT/usr/include" || { echo "missing target headers" >&2; exit 1; }
if ! test -f "$SYSROOT/usr/lib/libc.so.6" && ! test -f "$SYSROOT/lib64/libc.so.6"; then
    echo "missing target libc" >&2; exit 1
fi
tmp="$(mktemp -d /work/cross-verify.XXXXXXXX)"
trap 'rm -rf "$tmp"' EXIT
printf '#include <stdio.h>\nint main(void){puts("target-c");return 0;}\n' > "$tmp/check.c"
printf '#include <iostream>\nint main(){std::cout << "target-cxx";return 0;}\n' > "$tmp/check.cpp"
"$TOOLS/$TARGET-gcc" "$tmp/check.c" -o "$tmp/check-c"
"$TOOLS/$TARGET-g++" "$tmp/check.cpp" -o "$tmp/check-cxx"
for binary in "$tmp/check-c" "$tmp/check-cxx"; do
    header="$("$TOOLS/$TARGET-readelf" -h "$binary")"
    printf '%s\n' "$header" | grep -Eq 'Class:[[:space:]]+ELF64' || exit 1
    printf '%s\n' "$header" | grep -Eq 'Machine:[[:space:]]+Advanced Micro Devices X86-64' || exit 1
    printf '%s\n' "$header" | grep -Eq 'Type:[[:space:]]+(DYN|EXEC)' || exit 1
    program_headers="$("$TOOLS/$TARGET-readelf" -l "$binary")"
    printf '%s\n' "$program_headers" | grep -q 'Requesting program interpreter' || {
        echo "missing dynamic interpreter" >&2; exit 1;
    }
    interp="$(printf '%s\n' "$program_headers" | sed -n 's/.*Requesting program interpreter: \([^]]*\)\].*/\1/p')"
    case "$interp" in
        /lib/*|/lib64/*|/usr/lib/*|/usr/lib64/*) ;;
        *) echo "invalid target interpreter: $interp" >&2; exit 1 ;;
    esac
    dynamic="$("$TOOLS/$TARGET-readelf" -d "$binary")"
    if printf '%s\n' "$dynamic" | grep -E 'NEEDED.*\[/' ; then
        echo "absolute library dependency" >&2; exit 1
    fi
done
'''


def verify_cross_toolchain(build: Path, installed: Path, *, target: str,
                           original_workspace: Path | None = None) -> None:
    """Fail closed on unavailable target tools, linking failures or wrong ELF output."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", target):
        raise CrossToolchainVerificationError("invalid target triplet")
    build, installed = Path(build), Path(installed)
    try:
        mounts = _workspace_mounts(build, installed)
        # Verification never needs to modify the candidate installed filesystem.
        mounts[3] = "--ro-bind"
        command = _base_command() + mounts
        if original_workspace is not None:
            original = Path(original_workspace).resolve(strict=True)
            relocated = Path(installed).resolve(strict=True)
            if original == relocated or original in relocated.parents or relocated in original.parents:
                raise CrossToolchainVerificationError("relocation workspace overlaps original")
            # The sandbox exposes only /work and /toolchain, not either host path.
            # Reject accidental exposure of the original tree inside the sandbox.
            command += ["--setenv", "DISTRO_ORIGINAL_HOST_PATH", str(original)]
        command += ["--setenv", "PATH", "/toolchain/tools/bin:/usr/bin:/bin",
                    "--setenv", "HOME", "/work", "--setenv", "LC_ALL", "C",
                    "--", "/bin/bash", "-c", CHECK_SCRIPT, "cross-verify", target]
        subprocess.run(command, check=True, env={"PATH": os.defpath},
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    except (SandboxError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = exc.stderr.decode(errors='replace')[-1000:] if isinstance(exc, subprocess.CalledProcessError) and isinstance(exc.stderr, bytes) else str(exc)
        raise CrossToolchainVerificationError(f"cross-toolchain verification failed: {detail}") from exc
