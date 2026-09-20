# G1 chroot prototype

This prototype explores the first Generation-1 package set from a clean branch
based on `main`.

Public prototype interface:

```sh
./product/scripts/build g1-chroot
./product/scripts/manage install g1-chroot
```

`g1-chroot` is a desired-state manifest. It lists only the packages that belong
to the set, each package's upstream location, and its management policy.

The manifest does not pin concrete versions, checksums, build commands, or
recipes. Build is responsible for discovering an appropriate upstream version
from the declared policy, deriving or locating a recipe, building package
artifacts, and producing a `g1-chroot` meta-package whose runtime dependencies
represent the resolved package set.

The first functional target is a chroot containing GNU Bash and GNU Coreutils
(`ls`) without BusyBox.
