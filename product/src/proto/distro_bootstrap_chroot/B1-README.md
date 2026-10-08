# B1.1 — isolated cross-binutils proof (prototype)

B0 established that unprivileged Bubblewrap works on the tested Arch VM. B1.1 now builds GNU binutils from independently pinned upstream source under a private `/work` prefix. This experiment does **not** construct GCC, libc, a complete sysroot, or an installable Distro package.

## Reproduction

Run from the repository root as an ordinary user:

```sh
python3 product/src/proto/distro_bootstrap_chroot/b1_binutils.py --out /tmp/distro-b1-binutils-result.json
```

The runner downloads an upstream archive outside the sandbox, verifies its pinned SHA-512 **before** extraction, and builds with the already tested host compiler inside a network-isolated Bubblewrap mount/user/PID namespace. The isolated filesystem binds host tool/runtime directories read-only, with only `/work` writable. It does not request root privilege. By design, the resulting linker/assembler are host-executable cross tools, not yet Distro-native tools.

The SHA-512 was taken from the upstream `sha512.sum`; its signature has not been verified. A digest only pins exact bytes; it does not establish upstream authorship. GPG verification and cache/source trust are future experiments.

## Evidence and gates

The JSON result records source digest, download outcome, configure/build/install exit status, selected compiler environment, build logs (paths under the retained `--workspace` directory when supplied), prefixed tool version/target, and a no-libc relocatable object test produced by the prefixed assembler and linker. No host `as` or `ld` fallback is allowed in those acceptance checks. The test intentionally does not assert linker hermeticity; host libraries are still needed by the binutils executables, and the cross linker could still have compiled-in path defaults. The next B1 slice must inventory ELF runtime closure and linker search directories.

Use `--workspace /some/private/directory` to preserve source, build, installed prefix, and logs for inspection. Without it, the runner uses a temporary directory and retains only the result report. Do not reuse a workspace containing valuable files: the runner refuses any existing nonempty workspace.

A pass is specific to the host and version exercised; no accepted Product Design or Functional Set is created here.
