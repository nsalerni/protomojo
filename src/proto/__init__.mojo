# ===----------------------------------------------------------------------=== #
# Copyright (c) 2026 the grpc-mojo contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
# ===----------------------------------------------------------------------=== #

"""Protobuf binary wire format, proto3 JSON, and message runtime for Mojo.

Implements the [protobuf encoding](https://protobuf.dev/programming-guides/encoding/)
in two layers: `proto.wire` provides the low-level primitives (`WireWriter`,
`WireReader`, ZigZag transforms, wire-type constants), and `proto.message`
provides the `ProtoMessage` trait with the generic `encode`/`decode` entry
points. `proto.json` adds strict JSON for generated messages made from supported
scalar, enum, ordinary message, and map fields.
Correctness is pinned by the Google protobuf conformance suite (1476/1476 proto3
binary and JSON tests pass), golden bytes, and bidirectional JSON checks against
Python `protobuf`.

Message types are normally generated from `.proto` files by
`tools/protoc-gen-mojo`; any type implementing `ProtoMessage` works the
same way:

```mojo
from proto import decode, encode

var req = EchoRequest()
req.message = "hello"
var bytes = encode(req)
var back = decode[EchoRequest](Span(bytes))
```

Standalone by design: depends only on the standard library.
"""

from .message import ProtoMessage, decode, encode
from .json import (
    AnyJsonPayload,
    JsonParseOptions,
    JsonPrintOptions,
    ProtoJsonTypeResolver,
    ProtoJsonMessage,
    ProtoJsonReader,
    ProtoJsonWriter,
    any_type_name,
    decode_json,
    encode_json,
    extract_any_json_payload,
    parse_any_json_payload,
    print_any_json_payload,
)
from .wire import (
    MAX_DECODE_DEPTH,
    MAX_VARINT_LEN,
    WIRE_FIXED32,
    WIRE_FIXED64,
    WIRE_LEN,
    WIRE_VARINT,
    WireReader,
    WireWriter,
    zigzag_decode32,
    zigzag_decode64,
    zigzag_encode32,
    zigzag_encode64,
)
