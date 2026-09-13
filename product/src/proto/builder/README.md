# Builder discovery prototype

Prototype of the first Build discovery slice.

Input is a package name and upstream GitHub repository URL.

Discovery order:

1. determine the latest stable upstream version;
2. inspect that version's source tree;
3. search upstream documentation for build instructions;
4. extract documented build tools and commands;
5. only when documentation is insufficient, inspect source-tree build-system markers.

Documentation takes precedence over structural inference.

Run from the repository root:

```sh
python3 product/src/proto/builder/discover.py product/src/proto/builder/example-manifest.json
```

The initial prototype supports public github.com repository URLs only.
