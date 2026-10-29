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
    "$TOOLS/$TARGET-readelf" -l "$binary" | grep -q 'Requesting program interpreter' || {
        echo "missing dynamic interpreter" >&2; exit 1;
    }
done
'''


def verify_cross_toolchain(build: Path, installed: Path, *, target: str) -> None:
    """Fail closed on unavailable target tools, linking failures or wrong ELF output."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", target):
        raise CrossToolchainVerificationError("invalid target triplet")
    build, installed = Path(build), Path(installed)
    try:
        command = _base_command() + _workspace_mounts(build, installed)
        command += ["--setenv", "PATH", "/toolchain/tools/bin:/usr/bin:/bin",
                    "--setenv", "HOME", "/work", "--setenv", "LC_ALL", "C",
                    "--", "/bin/bash", "-c", CHECK_SCRIPT, "cross-verify", target]
        subprocess.run(command, check=True, env={"PATH": os.defpath},
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    except (SandboxError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = exc.stderr.decode(errors='replace')[-1000:] if isinstance(exc, subprocess.CalledProcessError) and isinstance(exc.stderr, bytes) else str(exc)
        raise CrossToolchainVerificationError(f"cross-toolchain verification failed: {detail}") from exc
