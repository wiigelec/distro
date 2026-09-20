# G1 chroot prototype

This prototype explores the first Generation-1 package set from a clean branch
based on `main`.

Public prototype interface:

```sh
./product/scripts/build g1-chroot
./product/scripts/manage install g1-chroot
```

`g1-chroot` is a desired-state manifest. Each package entry contains exactly:

- package name;
- upstream discovery URL;
- management policy: `stable`, `lts`, or `bleeding-edge`.

The manifest does not pin concrete versions, checksums, build commands, or
recipes. Build owns those decisions and generated state.

For `stable` packages Build now:

1. selects the newest stable source release from the upstream release index;
2. downloads and hashes the source;
3. safely extracts it and derives a candidate recipe from source-tree evidence;
4. executes every candidate recipe in the Generation-0 Arch environment;
5. stages successful installs under a package-specific `DESTDIR`;
6. preserves each package's build log and reports all failures together.

`lts` and `bleeding-edge` are recognized manifest values but intentionally fail
until their selection semantics are prototyped.

Run:

```sh
./product/scripts/build g1-chroot
```

Use `--jobs N` to control build parallelism. Generated source archives, work
trees, candidate recipes, build logs, staged roots, and the aggregate result are
written below `/tmp/distro-g1-chroot` by default.

Candidate recipes are still prototype-generated evidence, not accepted product
recipes. A failed package does not prevent the remaining packages from being
attempted. The aggregate result identifies failed commands and points to the
per-package logs so recipe derivation can be refined from actual build behavior.

Once all five packages stage successfully, the next slice packages those staged
roots, publishes a prototype package repository plus the generated
`g1-chroot` meta-package, and lets Manage install that closure.

The first functional target remains a chroot containing GNU Bash and GNU
Coreutils (`ls`) without BusyBox.
