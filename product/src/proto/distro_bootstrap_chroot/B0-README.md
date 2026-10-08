# B0 — Host qualification experiment

This is a **prototype host-observation slice**. It does not establish accepted Product Design or import LFS package selections, build instructions, or version baselines.

## Goal

Record what a foreign host can actually provide before constructing Distro's temporary cross-toolchain. Host capabilities are *observed*, not assumed from the operating-system distribution name. The target triple, compatibility floors, isolation mechanism, and source trust policy remain hypotheses.

## Execute

From the repository root:

```sh
python3 product/src/proto/distro_bootstrap_chroot/host_probe.py \
  --out /tmp/distro-b0-host-report.json
```

The probe checks command locations and version banners, host/kernel identity, possibly contaminating build environment variables, and builds/executes a minimal C and C++ program in a temporary directory. If `readelf` is present, it records ELF interpreter and dynamic dependency evidence. No network downloads or privileged operations occur. The compiler probe uses the host compiler only; it is not the target-native handoff proof.

## Reporting and gates

A `provisional-pass` means required commands exist and host C/C++ compile/execute checks succeeded. It does **not** mean isolation works or that minimum kernel/tool versions are established. Inspect `observations_requiring_review`, the ELF records, and environment values. The `status` is `blocked` if required commands are missing or either compile/execute probe fails.

`host-contract.json` intentionally contains no fabricated minimum version numbers. After collecting evidence on actual hosts, establish explicit suitability criteria and test real process/mount namespace or privileged chroot isolation separately. Avoid storing private environment variable values in reports: only PATH is recorded, and other variables are recorded by presence.

## B0 graduation criteria

1. Select and record the supported host/toolchain ABI and target triple based on real compatibility evidence.
2. Demonstrate selected filesystem/process isolation on the actual host, including cleanup.
3. Identify all host-derived executable and library dependencies needed for B1.
4. Freeze a reviewed host contract with justified minimum versions and contamination controls.
5. Produce repeatable machine-readable results from at least one supported host.

Until those are met, B0 is investigation—not a completed bootstrap qualification.
