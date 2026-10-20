# Cross-toolchain construction

The host qualification, dependency-closure, source acquisition, and cross-toolchain
modules implement separate functional boundaries. This directory does **not**
contain a pinned upstream package catalog. A reviewed complete source inventory
and installed host mappings are required for each new execution.

First run `preflight.py --manifest <inventory.json> --output <baseline.json>`
as an unprivileged user. The manifest must include the complete selected bootable
source and build/runtime dependency inventory, not merely the toolchain package
names. Then run:

```sh
python3 product/src/bootstrap/cross_toolchain.py \
  --baseline /absolute/path/to/baseline.json \
  --workspace /absolute/path/to/empty-workspace --jobs 4
```

Only explicitly reviewed recipe commands execute. Builds use Bubblewrap with
read-only host paths, no network, and writable workspace/toolchain directories.
Source archives are verified against execution-local locks before extraction.
The supported order is Binutils, bootstrap GCC, Linux API headers, glibc, then
shared compiler/C++ runtime. No source versions are inferred by the runner.

Each stage retains its log. The construction fails closed when any recipe step,
target executable, ELF inspection, C/C++ link or target runtime execution fails.
On success it produces an external SHA-256 digest and member inventory with the
standalone `cross-toolchain-root.tar.xz` root handoff. A passing repository
validator is **not** evidence that a real toolchain was built; host execution
and review of the retained evidence remain mandatory.

The recipes retain **experimental** status until verified on the intended host.
A failed run retains its work directory; a new run uses a fresh workspace rather
than implicitly treating unvalidated partial output as a checkpoint. Authenticated
source methods not supported by `source_artifacts.py` remain fail-closed.
