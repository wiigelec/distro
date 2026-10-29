"""Host capability qualification before host-executed package construction."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile


class HostRequirementsError(RuntimeError):
    """A required host capability is unavailable or unqualified."""


# LFS 13.1-systemd Chapter 2 minimums. Both compilers use the GCC floor.
# A present tool with an unparseable version is not considered qualified.
MINIMUMS = {
    "bash": ("bash", "3.2"),
    "binutils": ("ld", "2.13.1"),
    "bison": ("bison", "2.7"),
    "coreutils": ("sort", "8.1"),
    "diffutils": ("diff", "2.8.1"),
    "findutils": ("find", "4.2.31"),
    "gawk": ("gawk", "4.0.1"),
    "gcc": ("gcc", "5.4"),
    "g++": ("g++", "5.4"),
    "grep": ("grep", "2.5.1a"),
    "gzip": ("gzip", "1.3.12"),
    "m4": ("m4", "1.4.10"),
    "make": ("make", "4.0"),
    "patch": ("patch", "2.5.4"),
    "perl": ("perl", "5.8.8"),
    "python3": ("python3", "3.4"),
    "sed": ("sed", "4.1.5"),
    "tar": ("tar", "1.22"),
    "texinfo": ("makeinfo", "5.0"),
    "xz": ("xz", "5.0.0"),
}


def _version(value: str) -> tuple[int, ...]:
    """Compare numeric components, including historic suffixes such as 2.5.1a."""
    match = re.search(r"(?<![A-Za-z0-9])([0-9]+(?:\.[0-9]+)+)([a-z]?)", value, re.I)
    if match is None:
        raise HostRequirementsError(f"cannot determine tool version: {value[:120]!r}")
    parts = tuple(int(v) for v in match.group(1).split("."))
    return parts + ((ord(match.group(2).lower()) - ord('a') + 1,) if match.group(2) else (0,))


def _at_least(observed: str, minimum: str) -> bool:
    a, b = _version(observed), _version(minimum)
    size = max(len(a), len(b))
    return a + (0,) * (size - len(a)) >= b + (0,) * (size - len(b))


def _capture(args: list[str]) -> str:
    try:
        cp = subprocess.run(args, capture_output=True, text=True, timeout=20, check=True,
                            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise HostRequirementsError(f"host command failed: {args[0]}: {exc}") from exc
    return (cp.stdout + "\n" + cp.stderr).strip()


def _check_tools() -> None:
    for name, (command, minimum) in MINIMUMS.items():
        exe = shutil.which(command, path="/usr/bin:/bin")
        if not exe:
            raise HostRequirementsError(f"missing required host tool: {name} ({command})")
        output = (_capture([exe, "-e", 'printf "%vd\n", $^V']) if name == "perl"
                  else _capture([exe, "--version"]))
        # Uutils coreutils is a separately qualified implementation.
        if name == "coreutils" and "uutils" in output.lower():
            minimum = "0.8"
        if not _at_least(output, minimum):
            raise HostRequirementsError(f"{name} below required {minimum}: {output.splitlines()[0]}")
    for command in ("readelf", "as", "ld", "gcc", "g++", "bwrap"):
        if not shutil.which(command, path="/usr/bin:/bin"):
            raise HostRequirementsError(f"missing required host command: {command}")


def _check_shell_tools() -> None:
    bash = Path('/bin/bash')
    shell = Path('/bin/sh')
    if not bash.is_file() or not shell.exists() or shell.resolve() != bash.resolve():
        raise HostRequirementsError('/bin/sh must resolve to /bin/bash for this baseline')
    awk = Path('/usr/bin/awk')
    gawk = Path('/usr/bin/gawk')
    if not awk.exists() or not gawk.is_file() or awk.resolve() != gawk.resolve():
        raise HostRequirementsError('/usr/bin/awk must resolve to gawk')
    yacc = Path('/usr/bin/yacc')
    if not yacc.is_file():
        raise HostRequirementsError('/usr/bin/yacc must be available')
    # A yacc wrapper script is permitted; it must actually work.
    _capture([str(yacc), '--version'])


def _check_native_compilers() -> None:
    machine = _capture(['/usr/bin/gcc', '-dumpmachine']).splitlines()[0]
    if not machine.startswith('x86_64-'):
        raise HostRequirementsError(f'unsupported native GCC host triplet: {machine}')
    for compiler, suffix, source in (
        ('gcc', '.c', '#include <stdio.h>\nint main(void){puts("host-c-ok");return 0;}\n'),
        ('g++', '.cpp', '#include <iostream>\nint main(){std::cout << "host-cxx-ok";return 0;}\n'),
    ):
        with tempfile.TemporaryDirectory(prefix='distro-host-probe-') as tmp:
            src = Path(tmp) / ('probe' + suffix)
            out = Path(tmp) / 'probe'
            src.write_text(source)
            _capture([f'/usr/bin/{compiler}', str(src), '-o', str(out)])
            result = _capture([str(out)])
            if result != ('host-c-ok' if compiler == 'gcc' else 'host-cxx-ok'):
                raise HostRequirementsError(f'{compiler} compiled host executable failed')


def qualify_host() -> None:
    """Fail before workspace mutation if host prerequisites are not satisfied."""
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise HostRequirementsError('cross-toolchain requires x86_64 Linux host')
    if not _at_least(platform.release(), '5.10'):
        raise HostRequirementsError('Linux kernel 5.10 or later required')
    if os.geteuid() == 0:
        raise HostRequirementsError('host construction must run unprivileged')
    _check_tools()
    _check_shell_tools()
    _check_native_compilers()
