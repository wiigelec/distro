# B0 — Bubblewrap isolation experiment

**Status:** exploratory, not an accepted Build isolation policy.

## Execution

From the `proto/distro-bootstrap-chroot` repository root, **as a regular user**:

```sh
python3 product/src/proto/distro_bootstrap_chroot/isolation_probe.py \
  --out /tmp/distro-b0-isolation-report.json
```

The program attempts a nonprivileged Bubblewrap environment with separate user,
PID, network, IPC, UTS, cgroup, and mount namespaces. It bind-mounts host executable
and runtime directories read-only; only an ephemeral work directory and a private
`/tmp` are writable. It verifies PID namespace behavior, invisible host `/tmp`,
read-only `/usr`, and compilation/execution of C and C++ test binaries.

No privileged fallback, root invocation, networking, package installation, source
download, or persistent host filesystem mutation is permitted. A denial from
unprivileged user namespaces is a **blocked finding**, not a request to silently
run with elevated privileges. All temporary work is deleted upon completion.

## Gate / caveats

A `provisional-pass` establishes that this host can run the prescribed isolation
experiment, **not** that the bootstrap environment is independent of host
libraries or toolchains. Separate B1 experiments must inspect compiler search
paths, dynamic interpreters and dependency closure, and demonstrate a new target
sysroot. Record the full report as evidence; do not promote this probe to
accepted Product Design on its own.

The list of read-only host mounts is consciously a permissive experiment; it is
not the eventual minimal isolation allowlist. The B0 probe does not test
isolation of additional credentials or other host files under `/etc`.
