# Bootstrap phase build wrapper (prototype)

From the repository root:

```sh
./product/scripts/build cross-toolchain --root ~/distro-bootstrap-chroot/root
```

The first GVE file creation does **not** set the Git executable bit. If the new script is not executable, use `chmod +x product/scripts/build` in the working tree (and record/commit the mode adjustment separately), or invoke it with `python3 product/scripts/build cross-toolchain --root ...`.

The wrapper reads `cross-toolchain/cross-toolchain-manifest.json` **in listed order**. Each executable package is built using its JSON recipe and the existing generic cross-runner. Host versions are detected on each invocation; no fixed version lock is used. The package runner builds into a private, per-attempt workspace and the wrapper copies the successfully built prefix into the requested root. It never runs as root.

**Resume policy:** completed packages get stamps at `<root>/.distro-bootstrap/stamps/cross-toolchain/<package>.json`. A stamp is honored only when the host version, package manifest entry, recipe, generic runner, and installed file content match. A failed package is never stamped, and the next invocation starts a fresh attempt for that package, retaining prior workspaces, logs, and reports for diagnosis. This is **package-level** resume, not step-level continuation of a failed configure/make. Unresolved manifest entries block the phase rather than silently skipping required packages.

**Console progress** includes package position, detected host version, acquire/build status, each `STEP` observed in the build log, a heartbeat around every 30 seconds, elapsed time and the relevant log/result location on failure. Full detailed build output remains in the retained workspace log.

**Current limitations:** Binutils is the only executable package in the manifest. GCC, Linux API headers and glibc are unresolved, so a complete phase run will stop at the first unresolved entry. Changed host versions or changed recipe/runner inputs with already-installed package files fail closed and require a clean target root; the wrapper does not automatically remove old toolchain files. Install promotion currently copies directly into the target root; interruptions during this operation can leave partial un-stamped files. Use an initially empty dedicated bootstrap root, not a live filesystem. The previously observed source-checksum authentication limitation remains unchanged.
