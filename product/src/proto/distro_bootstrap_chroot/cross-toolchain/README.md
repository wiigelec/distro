# Phase 1 — Cross-toolchain

Active files: `cross-toolchain-manifest.json` (host-version discovery and upstream sources), `cross_runner.py` (generic executor) and `recipes/` (package-specific JSON build instructions).

Run from the repository root with a fresh, empty workspace:

```sh
python3 product/src/proto/distro_bootstrap_chroot/cross-toolchain/cross_runner.py \
  --package binutils --workspace /var/tmp/distro-cross-new \
  --out /tmp/distro-cross-result.json
```

Host versions are discovered on **every execution**; no lock file controls subsequent runs. `host/` contains host qualification probes; `experiments/` preserves historical cross-toolchain trials and audits, not current build instructions.

Binutils, GCC, Linux API headers, and glibc have executable prototype recipes. A complete clean build and dependency closure remain unproven.

The installed bootstrap root is mounted at `/toolchain` for dependent builds. Target headers reside at `/toolchain/usr/include`, and the initial GCC uses `--with-sysroot=/toolchain`. The cross-toolchain must pass build and export validation before temporary-tools begins.
