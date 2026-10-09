# Bootstrap phase build wrapper (prototype)

From the repository root:

```sh
./product/scripts/build cross-toolchain --root ~/distro-bootstrap-chroot
```

`--root` identifies a bootstrap **project directory**, not the installation prefix itself. The wrapper creates two siblings under this directory:

```text
~/distro-bootstrap-chroot/
├── root/                  # installed package filesystem only (eventual chroot)
└── .distro-bootstrap/     # build workspaces, logs, results, package stamps
    ├── work/cross-toolchain/
    └── stamps/cross-toolchain/
```

The wrapper builds packages in manifest order using host-version discovery at each run and the package-specific JSON recipes. Successful package files go to `<project>/root/`; the cross-toolchain prefix used for dependent packages is also `<project>/root/`. Workspaces, downloaded sources, build logs, result JSON, and stamps remain under `<project>/.distro-bootstrap/`, entirely outside the future chroot.

A verified stamp resumes at the next package. Failed package attempts retain diagnostics and rerun in new workspaces; resumes currently occur at **package** rather than recipe-step granularity. Changes in host version, recipe, runner, or installed artifacts invalidate completion. The current implementation refuses overwriting packages already installed from changed inputs, so those require a clean project root for rebuilding.

**Legacy layouts:** Older runs placed `.distro-bootstrap` inside the directory given to `--root`. The new wrapper rejects nested `root/.distro-bootstrap` rather than moving or deleting user files automatically. For an existing project, back up the old state and reconcile stamps carefully before adopting the new layout; a fresh project directory is safest for the first integration test. Do not invoke the updated wrapper with a trailing `/root` in `--root`, or it will create a nested filesystem.

Progress is streamed to the terminal, including package position, current recipe step, elapsed time, and diagnostic paths on failure. The build operates as a non-root user, and the bootstrap phases remain experimental.
