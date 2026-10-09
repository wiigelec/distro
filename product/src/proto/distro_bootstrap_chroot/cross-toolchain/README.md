# Phase 1 — Cross-toolchain

Active files: `cross-toolchain-manifest.json` (host-version discovery and upstream sources), `cross_runner.py` (generic executor) and `recipes/` (package-specific JSON build instructions).

Run from the repository root with a fresh, empty workspace:

```sh
python3 product/src/proto/distro_bootstrap_chroot/cross-toolchain/cross_runner.py \
  --package binutils --workspace /var/tmp/distro-cross-new \
  --out /tmp/distro-cross-result.json
```

Host versions are discovered on **every execution**; no lock file controls subsequent runs. `host/` holds B0 probes and `experiments/` preserves the previous source-pinned B1 trial and audit **for history only**. Historical experiment documentation may reference old source-file locations; use the active path above for current builds.

Only Binutils has an executable recipe. GCC, Linux API headers, and glibc remain unresolved candidates. This is not yet a proven hermetic toolchain.
