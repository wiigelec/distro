# G1 chroot prototype

This prototype explores a Generation-1 package set built from a clean branch
based on `main`.

Public prototype interface:

```sh
./product/scripts/build g1-chroot
./product/scripts/manage install g1-chroot
```

`g1-chroot` is a desired-state manifest. Each package entry contains only a
package name, upstream discovery URL, and management policy.

For `stable` packages Build now:

1. selects the newest stable source release from the upstream release index;
2. downloads and hashes the source;
3. derives a candidate recipe from source-tree evidence;
4. builds and stages the package in the Generation-0 Arch environment;
5. packages the staged payload as a `.distro.tar.gz` artifact;
6. publishes a prototype `database.json`;
7. synthesizes a no-payload `g1-chroot` meta-package whose dependencies are the
   package names in the manifest.

The prototype repository is written to:

```text
/tmp/distro-g1-chroot/repository
```

Then Manage can resolve and install the generated closure:

```sh
./product/scripts/manage install g1-chroot
```

The default managed root is:

```text
/tmp/distro-g1-root
```

Manage verifies package checksums and embedded identity, resolves named
dependencies, checks owned-path conflicts, installs payloads, and records
installed state in `var/lib/distro/manage/installed.json` inside the target.

At this stage the meta-package expresses the complete G1 set closure. Precise
per-package runtime dependency discovery is intentionally still unresolved; the
five real packages currently publish with empty dependency lists, while
`g1-chroot` depends on all five. The generated GNU Info `usr/share/info/dir`
index is excluded from package ownership to avoid false cross-package ownership
collisions.

`lts` and `bleeding-edge` remain recognized but unimplemented management
policies.

The immediate acceptance target is:

```sh
sudo chroot /tmp/distro-g1-root /usr/bin/bash
/usr/bin/ls -l /
```

This intentionally uses `/usr/bin/bash` for the first closure proof. A
distro-owned filesystem package or equivalent merged-/usr policy can add
`/bin -> usr/bin` once the package/repository/Manage path is proven.
