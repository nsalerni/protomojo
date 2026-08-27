# Contributing to protomojo

Thanks for looking at the project. Wire and JSON behavior is checked against
Google's protobuf conformance suite and Python `protobuf`.

## Setup

```sh
curl -fsSL https://pixi.sh/install.sh | sh
git clone https://github.com/nsalerni/protomojo.git
cd protomojo
pixi install
pixi run test
```

## Style

- Public APIs follow the
  [Mojo docstring style](https://github.com/modular/modular/blob/main/mojo/stdlib/docs/docstring-style-guide.md).
- This repo targets Mojo 1.0: `def` only (no `fn`), `comptime` not `alias`,
  `std.`-prefixed imports, and explicit `.copy()` / `^` moves. Generated
  enums are Equatable wrapper structs (`value`, `name()`, `from_name()`),
  not a bare `Int32`. Tests are plain executables run by
  `tools/run_tests.py` (`mojo test` no longer exists).

## Checks

```sh
pixi run test
pixi run example
pixi run compliance    # if you change encode, decode, JSON, or codegen
```

Generated test protos and goldens should be regenerated, not edited:

```sh
pixi run gen-proto
pixi run gen-vectors
```

Fork, branch from `main`, and keep pull requests focused. Remaining work
is listed in [ROADMAP.md](ROADMAP.md). By contributing, you agree that
your contributions are licensed under [Apache License 2.0](LICENSE).
