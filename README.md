# protomojo

[![CI](https://github.com/nsalerni/protomojo/actions/workflows/ci.yml/badge.svg)](https://github.com/nsalerni/protomojo/actions/workflows/ci.yml)
[![Protobuf conformance](https://img.shields.io/endpoint?url=https%3A%2F%2Fnsalerni.github.io%2Fprotomojo%2Fconformance-badge.json)](https://nsalerni.github.io/protomojo/COMPLIANCE.html)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Protocol Buffers for **Mojo 1.0**: proto3 binary encoding, proto3 JSON, and a
`protoc` plugin. The runtime depends only on the Mojo standard library.

**[Compliance report](https://nsalerni.github.io/protomojo/COMPLIANCE.html)**
([Markdown](COMPLIANCE.md)) is regenerated on every CI run.

## Install

```sh
curl -fsSL https://pixi.sh/install.sh | sh
git clone https://github.com/nsalerni/protomojo.git
cd protomojo
pixi install
pixi run test
pixi run example
```

A conda recipe lives in [`recipe/`](recipe/).

## Usage

```sh
python3 -m grpc_tools.protoc -I proto \
  --plugin=protoc-gen-mojo=tools/protoc-gen-mojo \
  --mojo_out=src proto/my_service.proto
```

```mojo
from proto import decode, encode

var request = EchoRequest()
request.message = "hello"
var wire = encode(request)
var parsed = decode[EchoRequest](Span(wire))
```

JSON for generated messages that implement `ProtoJsonMessage`:

```mojo
from proto import decode_json, encode_json

var text = encode_json(request)
var parsed = decode_json[EchoRequest](text)
```

Unsupported message shapes do not implement the JSON trait, so they fail at
compile time instead of dropping fields. Type mappings:
[docs/JSON.md](docs/JSON.md). Code generator:
[docs/CODEGEN.md](docs/CODEGEN.md).

Runnable examples: [examples/README.md](examples/README.md).

## Features

- `WireWriter` / `WireReader` — varints, zigzag, packed fields, unknown fields
- `encode` / `decode` over the `ProtoMessage` trait
- Strict proto3 JSON for supported generated messages
- `protoc-gen-mojo` — proto3 messages, maps, oneofs, optional, imports, gRPC stubs

Out of scope: proto2, editions, and text format.

## Compliance

Google's official suite: **1476/1476** proto3 binary and JSON tests (`--enforce_recommended`).
The runner skips 1303 proto2 cases. Additional checks: Python `protobuf`
differentials, golden bytes, and deterministic wire mutations.

```sh
pixi run compliance
pixi run fuzz-wire-smoke
```

Current results: [COMPLIANCE.md](COMPLIANCE.md).

## Related packages

[grpc-mojo](https://github.com/nsalerni/grpc-mojo) uses this package for
messages and stubs.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE). Not affiliated with Google or Modular; "Protocol
Buffers" is a trademark of Google LLC and "Mojo" a trademark of Modular Inc.
