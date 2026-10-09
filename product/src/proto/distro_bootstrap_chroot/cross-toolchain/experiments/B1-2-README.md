# B1.2 — cross-Binutils boundary audit

Status: **prototype observation, not proven target-toolchain hermeticity**.

B1.1 built a host-executable assembler/linker from Distro-selected and digest-pinned Binutils source. B1.2 audits those retained files without running a rebuild or changing the workspace.

Run as an ordinary user on the machine that completed B1.1:

```sh
python3 product/src/proto/distro_bootstrap_chroot/b1_2_audit.py \
  --workspace /tmp/distro-b1-work \
  --out /tmp/distro-b1-2-audit-result.json
```

The report records tool and object SHA-256 hashes, ELF program interpreter, direct DT_NEEDED and RPATH/RUNPATH entries, linker emulations, configured sysroot output, and `ld --verbose` SEARCH_DIR values. It never invokes `ldd` or uses a linker to resolve arbitrary untrusted objects. Processes run unprivileged with a fixed minimal environment. Source/workspace files are read-only to this script; only an explicitly requested report is written.

**Two distinct dependency boundaries:** Host shared libraries loaded by the cross-assembler or cross-linker are expected while bootstrapping. Target search directories and eventual C runtime/startup objects must instead resolve to Distro's designated sysroot. A zero exit status means **audit observations were collected**, not that toolchain contamination is absent. If results reveal suspect paths, record them explicitly before cross-GCC or libc work.

B1.3 should introduce a deliberately empty target sysroot and a negative test showing that a target dynamic link cannot succeed through implicit host libc/startup objects. Only later should a real target libc be introduced.
