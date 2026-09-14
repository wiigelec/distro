# Builder prototype

This directory prototypes the Build package-production lifecycle.

The discovery slice accepts a package name and upstream GitHub repository URL,
selects the latest stable release/tag, inspects release-specific documentation
first, extracts documented build methods, and falls back to source-tree markers
only when documentation is insufficient.

The end-to-end slice currently uses curl as the fixture:

```text
manifest
  -> discovery
  -> candidate recipe
  -> clean OCI build environment
  -> source fetch + SHA-256
  -> build
  -> DESTDIR staging
  -> package metadata
  -> prototype package archive
  -> package verification
  -> artifact SHA-256 + result/provenance
```

Prototype policy is kept explicit. Discovery can report multiple upstream build
methods; recipe generation currently prefers CMake and supports end-to-end
execution only for curl. The clean build environment is `debian:12-slim` with a
declared bootstrap package set. That bootstrap set is prototype policy, not
dependency discovery.

Run discovery only:

```sh
python3 product/src/proto/builder/discover.py   product/src/proto/builder/example-manifest.json
```

Run the end-to-end curl prototype:

```sh
python3 product/src/proto/builder/pipeline.py   product/src/proto/builder/example-manifest.json   --output /tmp/distro-builder
```

The pipeline requires either Podman or Docker. Podman is preferred when both are
available.

A successful run writes approximately:

```text
/tmp/distro-builder/
├── result.json
└── curl/
    ├── discovery.json
    ├── recipe.json
    ├── source.tar.gz
    ├── src/
    ├── build/
    ├── stage/
    ├── build.log
    ├── packages/
    │   └── curl-<version>-<arch>-r1.distro.tar.gz
    └── result.json
```

The pipeline verifies the emitted archive before reporting success. Verification
checks archive path safety, embedded metadata, artifact SHA-256, and the expected
curl payload path `root/usr/bin/curl`.

A completed curl build can be checked again without rebuilding:

```sh
python3 product/src/proto/builder/acceptance.py   /tmp/distro-builder/curl/result.json
```

Or verify an artifact directly:

```sh
python3 product/src/proto/builder/verify.py   /tmp/distro-builder/curl/packages/curl-<version>-<arch>-r1.distro.tar.gz
```

The archive format, container image, bootstrap dependencies, method preference,
and recipe schema are deliberately prototype choices. They do not settle the
open product-design questions for Build.
