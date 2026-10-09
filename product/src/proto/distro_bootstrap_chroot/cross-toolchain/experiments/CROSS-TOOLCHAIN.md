# Distro bootstrap phase manifests (prototype)

The three experimental phases are **cross-toolchain**, **temporary tools**, and **extra tools**, mirroring only the stage progression of LFS Chapters 5–7. Distro's package inventories and recipes are independently chosen; no LFS package selections or instructions are imported.

## Version policy

Every execution probes the foreign host's current installed versions and attempts to resolve matching upstream source archives. No version locks, fixed release versions, or persistent source-selection caches govern future builds. Upgrading the host changes the version selected on the next invocation. A past JSON result is diagnostic evidence only.

Host distribution version strings may not correspond to upstream archive versions. Exact matching is required here; if the mapping is ambiguous or an upstream source cannot be authenticated/located, fail closed. GCC, glibc and Linux API headers are recorded as candidates whose recipes/source mappings are currently unresolved, **not** as completed phase inventory or runnable packages. Binutils is the only executable recipe in this increment.

For Binutils the runner runs `ld --version`, extracts its GNU Binutils version, constructs the upstream archive URL from the manifest, retrieves the current upstream `sha512.sum`, selects the exact archive entry, verifies the downloaded bytes, and runs `recipes/cross-binutils.json` in network-isolated Bubblewrap. The SHA-512 listing itself is fetched over HTTPS and **not signature authenticated**; this is a prototype trust limitation. Source acquisition occurs outside the network-isolated build environment.

Run in a **fresh** persistent directory, not the previous B1 workspace (nonempty directories are rejected):

```sh
python3 product/src/proto/distro_bootstrap_chroot/cross_runner.py \
  --package binutils --workspace /var/tmp/distro-cross-dynamic-1 \
  --out /tmp/distro-cross-dynamic-result.json
```

The result records the observed host version, resolved URL, SHA-512 and build outcome for audit, **not a reusable lock**. A rebuilt assembler/linker remains host-executable; isolation of target headers/startup objects and native handoff are unproven.
