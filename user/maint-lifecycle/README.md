# Package maintenance lifecycle prototype

This workspace is intentionally outside accepted Product architecture. It exercises the package-maintenance lifecycle one transition per CLI invocation.

## Layout

```
maint-lifecycle/
├── client/
│   ├── manage/
│   │   └── manage
│   └── root/
└── server/
    ├── build/
    │   └── build
    └── publish/
        └── artifacts/
```

## Tree walkthrough

The upstream project has tags 2.3.1 and 2.3.2. The first discovery uses a test ceiling so the historical 2.3.1 state can be exercised; the second discovery removes it.

```sh
cd maint-lifecycle

python3 server/build/build track tree https://github.com/Old-Man-Programmer/tree
python3 server/build/build discover tree --max-version 2.3.1
python3 server/build/build accept tree 2.3.1
python3 server/build/build prepare tree 2.3.1
python3 server/build/build build tree 2.3.1
python3 server/build/build publish tree 2.3.1

python3 client/manage/manage refresh
python3 client/manage/manage info tree
python3 client/manage/manage install tree
python3 client/manage/manage status tree
client/root/usr/bin/tree --version

python3 server/build/build discover tree
python3 server/build/build status tree
python3 server/build/build accept tree 2.3.2
python3 server/build/build prepare tree 2.3.2
python3 server/build/build build tree 2.3.2
python3 server/build/build publish tree 2.3.2

python3 client/manage/manage refresh
python3 client/manage/manage status tree
python3 client/manage/manage upgrade tree
python3 client/manage/manage info tree
client/root/usr/bin/tree --version

python3 client/manage/manage remove tree
python3 client/manage/manage list
```

Every command prints JSON and performs only its named transition. `discover` does not accept; `build` does not publish; `refresh` does not upgrade.

For deterministic/offline discovery testing, `discover` also accepts `--tags-file FILE`, where FILE is a JSON array of tag strings. For offline build testing, `build` accepts `--source-archive FILE`; normal operation fetches the recipe's upstream source URL.

The discovery version parser in this prototype is deliberately package-local to `tree`; it is not distro-wide version comparison policy.

## Validation in this workspace

The checked-in `run-log/` captures one complete lifecycle exercise. Discovery used the included tag fixture, which mirrors the real upstream 2.3.1/2.3.2 tags; build used small local source fixtures because this execution sandbox cannot make outbound build-time network requests. The normal CLI path still discovers GitHub tags and fetches the upstream source archive directly.
