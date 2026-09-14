#!/usr/bin/env python3
"""Boot an Install v0 image in QEMU and verify BusyBox ls."""

from __future__ import annotations

import argparse
import json
import os
import selectors
import shutil
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    qemu = shutil.which("qemu-system-x86_64")
    if qemu is None:
        raise RuntimeError("qemu-system-x86_64 is required")

    image = args.image.resolve()
    process = subprocess.Popen(
        [
            qemu, "-m", "256",
            "-display", "none",
            "-monitor", "none",
            "-serial", "stdio",
            "-no-reboot",
            "-drive", f"file={image},format=raw,if=virtio",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    transcript = ""
    command_sent = False
    deadline = time.monotonic() + args.timeout

    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            for key, _ in selector.select(timeout=0.25):
                chunk = os.read(key.fileobj.fileno(), 4096).decode(errors="replace")
                if not chunk:
                    continue
                transcript += chunk
                if not command_sent and "built-in shell (ash)" in transcript:
                    process.stdin.write(b"ls -al /\n")
                    process.stdin.flush()
                    command_sent = True
                if command_sent and " bin" in transcript and " etc" in transcript:
                    print(json.dumps({
                        "schema_version": 1,
                        "status": "success",
                        "image": str(image),
                        "test": "busybox-ls",
                    }, indent=2, sort_keys=True))
                    return

        raise RuntimeError(
            "VM did not complete the BusyBox ls smoke test; transcript follows:\n"
            + transcript[-12000:]
        )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
