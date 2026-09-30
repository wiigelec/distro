# Package maintenance lifecycle prototype

This workspace is intentionally outside accepted Product architecture. It exercises package maintenance one observable transition per CLI invocation.

## Layout

```text
maint-lifecycle/
├── client/
│   ├── manage/
│   │   └── manage
│   └── root/
└── server/
    ├── build/
    │   ├── build
    │   └── packages/
    │       └── <package>/<version>/
    │           ├── recipe-discovery.json
    │           └── recipe-working.json
    └── publish/
        └── artifacts/
```

`recipe-discovery.json` records what automatic discovery inferred for one upstream version.

`recipe-working.json` records the recipe proven to work for that version. If discovery testing succeeds, it is created automatically from the discovery recipe. If discovery testing fails, a maintainer can initialize it from discovery, correct it, and test it. A difference between the two files therefore records manual intervention directly.

Recipe testing validates both command success and the staged payload shape. For `tree`, the prototype requires `usr/bin/tree` and `usr/share/man/man1/tree.1`; a zero-exit install that writes outside staging is therefore still a failed recipe test.

## Maintenance flow

```text
track package
    ↓
discover initial/new upstream version
    ↓
accept version
    ↓
recipe-discover
    ↓
test-discovery
    ├── succeeds → recipe-working established automatically
    └── fails
          ├── working recipe exists → test-working
          ├── earlier-version working recipe exists → working-init carries it forward
          └── neither exists → needs-manual-intervention
    ↓
build from recipe-working
    ↓
publish
```

Every command prints JSON and performs only its named transition.

## Clean tree 2.3.1 exercise

From `user/maint-lifecycle`:

```sh
rm -rf \
  client/manage/package-db.json \
  client/manage/installed.json \
  client/root \
  server/build/manifest.json \
  server/build/state.json \
  server/build/packages \
  server/build/recipes \
  server/build/sources \
  server/build/work \
  server/build/stage \
  server/build/candidates \
  server/publish

python3 server/build/build track tree https://github.com/Old-Man-Programmer/tree
python3 server/build/build discover tree --max-version 2.3.1
python3 server/build/build accept tree 2.3.1
python3 server/build/build recipe-discover tree 2.3.1

# Expected to fail: tree's DESTDIR is the binary destination, not a staging root.
python3 server/build/build test-discovery tree 2.3.1

python3 server/build/build working-init tree 2.3.1
```

Edit `server/build/packages/tree/2.3.1/recipe-working.json` and change:

```text
make DESTDIR="$DESTDIR" PREFIX=/usr MANDIR=/usr/share/man install
```

to:

```text
make DESTDIR="$DESTDIR/usr/bin" MANDIR="$DESTDIR/usr/share/man" install
```

Then continue:

```sh
python3 server/build/build test-working tree 2.3.1
python3 server/build/build status tree 2.3.1
python3 server/build/build build tree 2.3.1
python3 server/build/build publish tree 2.3.1

python3 client/manage/manage refresh
python3 client/manage/manage info tree
python3 client/manage/manage install tree
python3 client/manage/manage status tree
client/root/usr/bin/tree --version
```

After the manual correction, `status tree 2.3.1` should report `manual_intervention: true`.


## Tree 2.3.2 upgrade exercise

After publishing and installing 2.3.1:

```sh
python3 server/build/build discover tree
python3 server/build/build accept tree 2.3.2
python3 server/build/build recipe-discover tree 2.3.2

# Expected to fail discovery again, but report the 2.3.1 working recipe.
python3 server/build/build test-discovery tree 2.3.2

# Carries forward the previous working recipe while replacing
# version-specific identity, source, and validation from 2.3.2 discovery.
python3 server/build/build working-init tree 2.3.2
python3 server/build/build test-working tree 2.3.2
python3 server/build/build status tree 2.3.2
python3 server/build/build build tree 2.3.2
python3 server/build/build publish tree 2.3.2
```

A carried-forward working recipe is still compared with the new version's
`recipe-discovery.json`, so package-specific maintenance remains visible.

## Offline fixtures

`discover` accepts `--tags-file FILE` for deterministic tag discovery.

`test-discovery`, `test-working`, and `build` accept `--source-archive FILE`; otherwise the source archive is fetched from the recipe URL.

The version parser and recipe discovery in this prototype are deliberately package-local to `tree`; they are not distro-wide package policy.
