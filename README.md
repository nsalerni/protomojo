# protomojo

[![CI](https://github.com/nsalerni/protomojo/actions/workflows/ci.yml/badge.svg)](https://github.com/nsalerni/protomojo/actions/workflows/ci.yml)
[![Protobuf conformance](https://img.shields.io/endpoint?url=https%3A%2F%2Fnsalerni.github.io%2Fprotomojo%2Fconformance-badge.json)](https://nsalerni.github.io/protomojo/COMPLIANCE.html)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**[📋 Compliance report](https://nsalerni.github.io/protomojo/COMPLIANCE.html)** ([Markdown](COMPLIANCE.md)). CI regenerates it on every run. Every check uses a reference implementation.

Protocol Buffers for **Mojo 1.0**: the binary wire format, a message
runtime, proto3 JSON for supported messages, and a `protoc` code
generator.

- `WireWriter` / `WireReader`: the proto3 wire format, including varints, zigzag,
  fixed32/64, length-delimited fields, tag coding, unknown-field capture,
  and the reference nesting-depth limit. Both reject malformed and hostile
  input.
- `ProtoMessage` trait + `encode[M]` / `decode[M]`: what generated code
  implements.
- `ProtoJsonMessage` trait + `encode_json[M]` / `decode_json[M]`: strict
  proto3 JSON for generated messages made from supported scalar, enum,
  ordinary message, and map fields. Unsupported message shapes do
  not implement the trait, so they fail at compile time instead of dropping
  fields.
- `tools/protoc-gen-mojo`: a protoc plugin emitting Mojo structs with
  every proto3 scalar kind, packed/unpacked repeated fields, maps, oneofs,
  proto3 `optional` (presence), nested and recursive messages (boxed to
  break trait-synthesis cycles), unknown-field preservation, cross-file
  imports, and service stubs for [grpc-mojo](https://github.com/nsalerni/grpc-mojo).

**Standalone by design:** the runtime depends only on the Mojo standard
library.

## Usage

Generate Mojo from your `.proto`:

```sh
python3 -m grpc_tools.protoc -I proto \
  --plugin=protoc-gen-mojo=tools/protoc-gen-mojo \
  --mojo_out=src proto/my_service.proto
```

The tested [address-book example](examples/codegen_roundtrip.mojo) builds a
message with scalar, repeated, map, and nested fields, then serializes and
parses it with the generated Mojo type. The
[ProtoJSON Any example](examples/protojson_any.mojo) packs a generated message,
prints it as JSON, parses it through the generated static resolver, and unpacks
the binary payload. Their schemas live beside the Mojo sources in `examples/`.

```sh
pixi run example
```

The task generates the Mojo modules in a temporary directory with
`protoc-gen-mojo`, then executes both round trips against that fresh output.

Generated messages made from supported fields also support JSON:

```mojo
from proto import decode_json, encode_json

var request = EchoRequest()
request.message = "hello"
var text = encode_json(request)
var parsed = decode_json[EchoRequest](text)
```

The current JSON mapping covers singular `int32`, `int64`, `uint32`,
`uint64`, `sint32`, `sint64`, `fixed32`, `fixed64`, `sfixed32`,
`sfixed64`, `float`, `double`, `bool`, `string`, `bytes`, enum, and ordinary
message fields. These fields may be singular or repeated, and nested messages
can contain more supported fields. Maps support every protobuf key type with
any scalar, enum, or ordinary message value. Enums preserve unknown numeric
values. When aliases share a number, JSON output uses the first declared name
for that number. Oneof members preserve selection even when the selected value
is the scalar default. Proto3 optional fields preserve presence, so a present
default value is printed and `null` clears ordinary optional fields. All nine
scalar wrapper types use their standard scalar JSON form. A wrapper field
keeps presence for default values, while `null` clears it. Timestamp values
use RFC 3339 text, accept numeric UTC offsets, and print normalized UTC with
the shortest exact 0, 3, 6, or 9 fractional digits. Duration values use signed
seconds with the
same canonical fractional precision and enforce protobuf's sign and range
rules. Field masks join snake-case paths with commas and convert each path to
lowerCamelCase. Printing rejects uppercase snake paths and malformed
underscores, matching the reference implementation.
`google.protobuf.Empty` prints as `{}` and works as a direct value or a message
field. `google.protobuf.Struct`, `Value`, and `ListValue` map to JSON objects,
arbitrary JSON values, and arrays. `NullValue` prints as JSON `null`, including
when it selects a oneof member or has optional presence. Repeated and mapped
`Value` entries accept JSON `null` as a value. Recursive message cycles work
when every type in the cycle has a complete JSON mapping.
`google.protobuf.SourceContext` and `Mixin` use their ordinary message-object
mapping. `google.protobuf.Any` uses a static resolver generated with the Mojo
message modules. The resolver recognizes the types in that protoc request,
including nested `Any` values and the special `value` form used by well-known
types. It only inspects the message name after the final slash in a type URL.
It never fetches the URL.

```mojo
from any_pb import Any
from proto import JsonParseOptions, decode_json
from vectors_pb_json_resolver import json_type_resolver

var options = JsonParseOptions(type_resolver=json_type_resolver())
var value = decode_json[Any](
    '{"@type":"type.googleapis.com/grpcmojo.test.EchoRequest",'
    '"message":"hello"}',
    options=options,
)
```

An empty `Any` maps to `{}` without a resolver. Parsing or printing any other
`Any` requires the generated resolver. Unknown type names fail locally.

## Verification

- **Google's official protobuf conformance suite: 1476/1476** proto3 binary
  and JSON tests pass with `--enforce_recommended`. The runner skips 1303
  proto2 cases because protomojo is proto3-only.
- Randomized differential testing against Python `protobuf` (the reference
  implementation): semantic equality plus byte-identical re-encoding.
- Deterministic binary wire mutations start from the checked-in golden vectors
  and malformed compliance cases. Python `protobuf` judges whether each input
  is valid. For valid inputs, it also checks the decoded meaning after
  protomojo re-encodes the message. CI runs 250 cases on each supported host,
  and a weekly job runs 20,000 cases from seed 20260824.
- Bidirectional proto3 JSON differential testing against Python `protobuf`
  covers 300 flat primitive messages in each direction, plus 20 accepted
  edge cases and 31 strict rejection cases. Singular enums add 200 cases from
  fixed seed 20260824 in each direction, 7 accepted edge cases, and 6 rejected
  forms. Singular nested messages add 200 cases in each direction. Repeated
  scalar and enum fields add 200 cases in each direction, 10 accepted edge
  cases, and 10 rejected forms from fixed seed 20260825. Repeated messages add
  another 200 cases in each direction, 6 accepted edge cases, and 6 rejected
  forms. String-key maps add 200 cases in each direction across every scalar
  and enum value type, 8 accepted edge cases, and 8 rejected forms. Integer and
  boolean map keys add another 200 cases in each direction, 8 accepted edge
  cases, and 8 rejected forms. Message-valued maps add 200 cases in each
  direction, 6 accepted edge cases, and 6 rejected forms. Oneofs add 200 cases
  in each direction, 10 accepted edge cases, and 8 rejected forms. Proto3
  optional fields add 200 cases in each direction across every scalar type,
  enums, and messages, plus 10 accepted edge cases and 8 rejected forms.
  `google.protobuf.Empty` adds 13 direct, field, and rejection cases. Scalar
  wrappers add 200 parse cases, 200 print cases, 6 direct cases, 12 accepted
  edge cases, and 10 rejected forms across all nine wrapper types. Timestamp
  adds 200 cases in each direction, 10 direct cases, 15 accepted edge cases,
  and 14 rejected forms across its full supported date range. Duration adds
  200 cases in each direction, 12 direct cases, 12 accepted edge cases, and
  10 rejected forms across singular and repeated fields. FieldMask adds 200
  cases in each direction, 11 direct cases, 12 accepted edge cases, and 10
  rejected forms. Recursive messages add 200 cases in each direction, 8
  accepted edge cases, and 10 strict parsing and depth-limit cases. The Struct
  family adds 200 cases in each direction, 18 direct cases, 17 accepted edge
  cases, and 18 rejected parse or print cases. Google descriptor messages add
  200 cases in each direction, 10 accepted edges, and 10 rejected forms,
  including `Option` fields that carry `Any`. `Any` adds 200 seeded cases in
  each direction, all 12 accepted cases from the official protobuf JSON suite,
  and 9 rejection cases judged by Python protobuf or the official C++ suite.
- Behavior is pinned by golden bytes generated with Python `protobuf`.
  The library never grades itself.

Current results: [COMPLIANCE.md](COMPLIANCE.md). CI regenerates the report
on every push, including the conformance run.

```sh
pixi run test          # unit tests (wire format, messages, generated code)
pixi run compliance    # differential + conformance; rewrites COMPLIANCE.md
pixi run example       # regenerate and run the address-book example
pixi run bench         # encode/decode throughput benchmarks
pixi run fuzz-wire-smoke  # 250 deterministic binary wire mutations
pixi run gen-proto     # regenerate test protos via protoc-gen-mojo
```

The mutation runner prints its seed and case count. On a mismatch it writes
the first input and its mutation history to
`build/wire-fuzz-failure.json` for exact reproduction.

## Status

Extracted from [grpc-mojo](https://github.com/nsalerni/grpc-mojo), where it
carries that project's messages. JSON supports recursive message cycles when
every referenced type has a complete mapping. Its special well-known type
mappings cover `Empty`, all nine scalar wrappers, `Timestamp`, `Duration`, and
`FieldMask`, plus `Struct`, `Value`, `ListValue`, and `NullValue`.
`SourceContext` and `Mixin` use the ordinary message mapping. `Any` resolves
types through generated static dispatch. Proto2 groups and extensions,
editions, and text format remain out of scope.

## License

[Apache-2.0](LICENSE). Not affiliated with Google or Modular; "Protocol
Buffers" is a trademark of Google LLC and "Mojo" a trademark of Modular Inc.
