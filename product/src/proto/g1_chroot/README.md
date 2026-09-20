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

The first implemented Build step resolves `stable` packages by inspecting their
upstream release indexes, excluding prerelease-looking archives, and selecting
the newest stable version it can identify. `lts` and `bleeding-edge` are
recognized manifest values but intentionally fail until their selection
semantics are prototyped.

Run:

```sh
./product/scripts/build g1-chroot
```

The command currently reports the concrete source version and source URL selected
for every package. Recipe discovery and package production are the next slice.

The first functional target remains a chroot containing GNU Bash and GNU
Coreutils (`ls`) without BusyBox.
