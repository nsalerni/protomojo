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

Fork, branch from `main`, and keep pull requests focused. By contributing,
you agree that your contributions are licensed under
[Apache License 2.0](LICENSE).
