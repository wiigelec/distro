#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from boot import PLAN_PATH, qemu_argv, require_root, require_tool
from guest import mounted_image
from resolve import load_json

AUTH_MARKER_OK = "DISTRO_PAM_LOGIN_PROOF_OK"
AUTH_MARKER_FAILED = "DISTRO_PAM_LOGIN_PROOF_FAILED"


def auth_plan() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "success",
        "mode": "plan",
        "kind": "booted-pam-login-proof",
        "input": "successful booted BLFS guest image",
        "authentication_path": "/usr/bin/login on a controlling PTY",
        "caller": "unprivileged nobody user",
        "test_user": "disposable local account",
        "session_proof": "authenticated login shell reports expected UID and user",
        "cleanup": "test account removed before shutdown",
        "success_marker": AUTH_MARKER_OK,
        "failure_marker": AUTH_MARKER_FAILED,
    }


def run(argv: list[str], *, capture: bool = False, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        check=True,
        capture_output=capture,
        text=True,
        input=input_text,
    )


def guest_probe_source() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pwd
import pty
import select
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

TEST_USER = "distro-m8-auth"
TEST_PASSWORD = "M8-PAM-Proof-2613!"
SESSION_MARKER = "DISTRO_PAM_LOGIN_SESSION_OK"
RESULT = Path("/var/lib/distro-m8-auth/result.json")
TRANSCRIPT = Path("/var/lib/distro-m8-auth/login-transcript.log")


def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, text=True, **kwargs)


def user_exists(name: str) -> bool:
    try:
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


def cleanup_user() -> None:
    if user_exists(TEST_USER):
        subprocess.run(["userdel", "-r", TEST_USER], check=False)


def read_until(fd: int, transcript: bytearray, needles: tuple[bytes, ...], timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        readable, _, _ = select.select([fd], [], [], 0.25)
        if not readable:
            continue
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        transcript.extend(chunk)
        lower = bytes(transcript).lower()
        if any(needle.lower() in lower for needle in needles):
            return bytes(transcript)
    raise RuntimeError(
        "timeout waiting for PTY text: "
        + ", ".join(x.decode(errors="replace") for x in needles)
    )


def child_status(pid: int) -> dict[str, int | None]:
    _, status = os.waitpid(pid, 0)
    if os.WIFEXITED(status):
        return {"exit_code": os.WEXITSTATUS(status), "signal": None}
    if os.WIFSIGNALED(status):
        return {"exit_code": None, "signal": os.WTERMSIG(status)}
    return {"exit_code": None, "signal": None}


def main() -> int:
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    login = shutil.which("login")
    if not login:
        raise RuntimeError("login executable not found")
    login_path = Path(login)
    login_stat = login_path.stat()
    login_setuid_root = login_stat.st_uid == 0 and bool(login_stat.st_mode & stat.S_ISUID)
    if not login_setuid_root:
        raise RuntimeError(f"{login_path}: login is not setuid-root")

    nobody = pwd.getpwnam("nobody")
    cleanup_user()
    transcript = bytearray()
    pid: int | None = None
    status: dict[str, int | None] = {"exit_code": None, "signal": None}
    marker_seen = False
    test_uid: int | None = None
    payload: dict[str, Any] = {}

    try:
        run(["useradd", "-m", "-s", "/bin/bash", TEST_USER])
        test_uid = pwd.getpwnam(TEST_USER).pw_uid
        run(["chpasswd"], input=f"{TEST_USER}:{TEST_PASSWORD}\n")

        pid, fd = pty.fork()
        if pid == 0:
            os.initgroups(nobody.pw_name, nobody.pw_gid)
            os.setgid(nobody.pw_gid)
            os.setuid(nobody.pw_uid)
            os.execve(
                str(login_path),
                [str(login_path)],
                {
                    "HOME": "/",
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "TERM": "dumb",
                },
            )
            raise AssertionError("execve returned")

        read_until(fd, transcript, (b"login:",), 30.0)
        os.write(fd, (TEST_USER + "\n").encode())
        read_until(fd, transcript, (b"password:",), 30.0)
        os.write(fd, (TEST_PASSWORD + "\n").encode())

        time.sleep(1.0)
        command = (
            "printf '" + SESSION_MARKER + " uid=%s user=%s\\n' "
            "\"$(id -u)\" \"$(id -un)\"; exit\n"
        )
        os.write(fd, command.encode())
        read_until(fd, transcript, (SESSION_MARKER.encode(), b"login incorrect"), 30.0)

        text = bytes(transcript).decode(errors="replace")
        expected = f"{SESSION_MARKER} uid={test_uid} user={TEST_USER}"
        marker_seen = expected in text
        if not marker_seen:
            raise RuntimeError("authenticated login shell marker not observed")

        status = child_status(pid)
        pid = None
        if status["exit_code"] != 0:
            raise RuntimeError(f"login child exited unexpectedly: {status}")

        payload = {
            "schema_version": 1,
            "status": "success",
            "kind": "pam-login-pty-proof",
            "login": str(login_path),
            "login_setuid_root": True,
            "caller_user": nobody.pw_name,
            "test_user": TEST_USER,
            "test_uid": test_uid,
            "session_marker": expected,
            "session_marker_seen": True,
            "child": status,
            "pam_session_opened": True,
            "authenticated_login_shell": True,
            "cleanup_required": True,
            "transcript": str(TRANSCRIPT),
        }
        return_code = 0
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "status": "failure",
            "kind": "pam-login-pty-proof",
            "login": str(login_path),
            "login_setuid_root": login_setuid_root,
            "caller_user": nobody.pw_name,
            "test_user": TEST_USER,
            "test_uid": test_uid,
            "session_marker_seen": marker_seen,
            "child": status,
            "pam_session_opened": False,
            "authenticated_login_shell": False,
            "error": str(exc),
            "transcript": str(TRANSCRIPT),
        }
        return_code = 1
    finally:
        if pid is not None:
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass
            try:
                child_status(pid)
            except ChildProcessError:
                pass
        TRANSCRIPT.write_bytes(bytes(transcript))
        cleanup_user()
        payload["test_user_removed"] = not user_exists(TEST_USER)
        RESULT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
'''


def inject_auth_proof(root: Path) -> None:
    target = root / "opt/distro-lfs-optimize"
    target.mkdir(parents=True, exist_ok=True)
    probe = target / "pam-login-probe.py"
    probe.write_text(guest_probe_source(), encoding="utf-8")
    probe.chmod(0o755)

    runner = target / "pam-login-proof.sh"
    runner.write_text(
        "#!/bin/bash\n"
        "set -o pipefail\n"
        "mkdir -p /var/lib/distro-m8-auth\n"
        "if /usr/bin/python3 /opt/distro-lfs-optimize/pam-login-probe.py "
        "> /var/lib/distro-m8-auth/probe-output.log 2>&1; then\n"
        f"  printf '{AUTH_MARKER_OK} pid1=%s systemd=%s\\n' "
        "\"$(cat /proc/1/comm)\" \"$(systemctl --version | head -1 | tr ' ' '_')\" "
        "> /dev/ttyS0\n"
        "  rc=0\n"
        "else\n"
        f"  printf '{AUTH_MARKER_FAILED} pid1=%s\\n' "
        "\"$(cat /proc/1/comm)\" > /dev/ttyS0\n"
        "  rc=1\n"
        "fi\n"
        "sync\n"
        "/usr/bin/systemctl --no-block poweroff\n"
        "exit $rc\n",
        encoding="utf-8",
    )
    runner.chmod(0o755)

    unit_dir = root / "etc/systemd/system"
    wants = unit_dir / "multi-user.target.wants"
    wants.mkdir(parents=True, exist_ok=True)

    for name in ("distro-boot-proof.service", "distro-blfs-proof.service"):
        (wants / name).unlink(missing_ok=True)

    unit = unit_dir / "distro-pam-login-proof.service"
    unit.write_text(
        "[Unit]\n"
        "Description=Booted PAM login/session proof\n"
        "After=local-fs.target systemd-user-sessions.service\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "ExecStart=/opt/distro-lfs-optimize/pam-login-proof.sh\n"
        "RemainAfterExit=yes\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n",
        encoding="utf-8",
    )
    link = wants / "distro-pam-login-proof.service"
    link.unlink(missing_ok=True)
    link.symlink_to("/etc/systemd/system/distro-pam-login-proof.service")


def collect_auth_evidence(root: Path, destination: Path) -> dict[str, Any] | None:
    source = root / "var/lib/distro-m8-auth"
    if destination.exists():
        shutil.rmtree(destination)
    if source.exists():
        run(["cp", "-a", str(source), str(destination)])
    result = source / "result.json"
    if not result.is_file():
        return None
    return json.loads(result.read_text(encoding="utf-8"))


def run_auth_proof(
    boot_work: Path,
    guest_work: Path,
    work: Path,
    timeout: int,
) -> dict[str, Any]:
    require_root()
    for tool in ("qemu-system-x86_64", "losetup", "mount", "umount", "cp"):
        require_tool(tool)

    boot_result_path = boot_work.resolve() / "boot/result.json"
    guest_result_path = guest_work.resolve() / "guest/result.json"
    if not boot_result_path.is_file():
        raise RuntimeError(f"missing boot result: {boot_result_path}")
    if not guest_result_path.is_file():
        raise RuntimeError(f"missing BLFS guest result: {guest_result_path}")

    boot_result = json.loads(boot_result_path.read_text(encoding="utf-8"))
    guest_result = json.loads(guest_result_path.read_text(encoding="utf-8"))
    if boot_result.get("status") != "success" or not boot_result.get("proof_marker_seen"):
        raise RuntimeError("boot-work is not a successful boot proof")
    if guest_result.get("status") != "success" or not guest_result.get("proof_marker_seen"):
        raise RuntimeError("guest-work is not a successful BLFS guest proof")
    live = guest_result.get("guest_result")
    if not isinstance(live, dict) or live.get("status") != "success":
        raise RuntimeError("guest-work lacks successful live BLFS evidence")
    if live.get("pid1") != "systemd":
        raise RuntimeError("BLFS guest proof did not run with systemd PID 1")

    base_image = Path(guest_result["guest_image"])
    kernel = Path(boot_result["kernel"])
    if not base_image.is_file() or not kernel.is_file():
        raise RuntimeError("proof inputs reference missing root image/kernel")

    auth_dir = work.resolve() / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    image = auth_dir / "pam-auth-root.ext4"
    mountpoint = auth_dir / "mnt"
    console_path = auth_dir / "qemu-console.log"
    evidence_dir = auth_dir / "evidence"
    result_path = auth_dir / "result.json"

    image.unlink(missing_ok=True)
    run(["cp", "--reflink=auto", "--sparse=always", str(base_image), str(image)])

    with mounted_image(image, mountpoint) as root:
        inject_auth_proof(root)

    definition = load_json(PLAN_PATH)
    argv = qemu_argv(definition, kernel, image)
    timed_out = False
    try:
        completed = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        console = completed.stdout or ""
        qemu_exit = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        raw = exc.stdout or ""
        console = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
        qemu_exit = None
    console_path.write_text(console, encoding="utf-8")

    with mounted_image(image, mountpoint) as root:
        auth_result = collect_auth_evidence(root, evidence_dir)

    marker_seen = AUTH_MARKER_OK in console
    auth_success = bool(
        auth_result
        and auth_result.get("status") == "success"
        and auth_result.get("session_marker_seen") is True
        and auth_result.get("pam_session_opened") is True
        and auth_result.get("authenticated_login_shell") is True
        and auth_result.get("test_user_removed") is True
    )
    payload = {
        "schema_version": 1,
        "status": "success" if marker_seen and auth_success else "failure",
        "kind": "booted-pam-login-proof",
        "input_guest_result": str(guest_result_path),
        "input_guest_image": str(base_image),
        "input_guest_final_root_sha256": live.get("final_root_sha256"),
        "input_systemd": live.get("systemd"),
        "input_kernel": live.get("kernel"),
        "auth_image": str(image),
        "qemu_command": argv,
        "qemu_exit_code": qemu_exit,
        "qemu_timed_out": timed_out,
        "console_log": str(console_path),
        "proof_marker": AUTH_MARKER_OK,
        "proof_marker_seen": marker_seen,
        "auth_result": auth_result,
        "pam_login_verified": auth_success,
        "review_required": not auth_success,
        "evidence_dir": str(evidence_dir),
    }
    result_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="verify the BLFS PAM/Shadow/systemd result with a real PTY login"
    )
    parser.add_argument("--boot-work", type=Path)
    parser.add_argument("--guest-work", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/lfs-optimize-m8-auth"))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()

    if args.plan:
        result = auth_plan()
    else:
        if args.boot_work is None or args.guest_work is None:
            parser.error("--boot-work and --guest-work are required unless --plan is used")
        result = run_auth_proof(args.boot_work, args.guest_work, args.work, args.timeout)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
