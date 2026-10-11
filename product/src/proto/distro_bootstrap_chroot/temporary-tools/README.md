# Temporary-tools stage — Bash chroot prototype

This stage begins by importing the verified `cross-toolchain-root.tar.xz` into a fresh `root/`, then cross-compiles GNU Bash as the first target-native program. It does **not** reuse the cross-toolchain build state, or create a second target root. The former numbered bootstrap states are retired.

From the Distro repository root, as an ordinary user:

```sh
./product/scripts/build temp-tools --root ~/distro-bootstrap-chroot \
  --cross-compiler ~/distro-bootstrap-chroot/artifacts/cross-toolchain-root.tar.xz
```

The `--root` argument names the *project directory*. `root/` is the installed filesystem; `.distro-bootstrap/` is the build workspace and stamp directory. The cross-compiler archive may remain in `artifacts/`, but the stage will refuse an occupied `root/` or `.distro-bootstrap/` without a valid matching `temp-tools` import marker. The archive digest must match its adjacent `.tar.xz.json` export report. On resume, the importer verifies the archive digest and key imported files, then skips Bash only if its stamp and binary remain valid.

Initial import and build are regular-user operations. The prototype uses unprivileged Bubblewrap to execute Bash with the imported root mounted as `/` for a builtins-only acceptance test. For an explicit, privileged *chroot* proof after successful build, run:

```sh
sudo chroot ~/distro-bootstrap-chroot/root /bin/bash --noprofile --norc
```

The initial implementation follows the host Bash major/minor version and downloads GNU Bash over HTTPS; the actual downloaded bytes are recorded by SHA-256. HTTPS transport alone does not authenticate upstream authorship. A detached-signature or independently pinned digest policy remains required for stronger provenance.

**Status:** experimental. Archive import and Bash execution are the first temporary-tools slice, not an accepted native tools package closure. An interrupted archive extraction leaves an occupied directory without a completion marker and fails closed on the next invocation. An interrupted Bash installation without a stamp similarly fails closed; automated rollback of such an interruption remains future work. The stage has no other executable package recipes yet.
