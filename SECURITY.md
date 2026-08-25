# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through
[protomojo security advisories](https://github.com/nsalerni/protomojo/security/advisories/new).
Do not include vulnerability details in a public issue. You should receive an
initial response within one week.

## Scope

protomojo parses untrusted Protocol Buffers binary data and proto3 JSON, then
generates Mojo code for proto3 schemas. The binary decoder rejects malformed
input and applies the protobuf reference nesting-depth limit. The JSON decoder
rejects malformed input and bounds nesting while skipping ignored unknown
values. The
[compliance report](COMPLIANCE.md) records the current reference tests.

ProtoJSON supports generated proto3 messages with scalar, enum, ordinary
message, repeated, map, oneof, and optional fields, including recursive
message graphs. Supported well-known types include `Empty`, the scalar
wrappers, `Timestamp`, `Duration`, `FieldMask`, `Struct`, `Value`, `ListValue`,
`NullValue`, `SourceContext`, `Mixin`, and resolver-backed `Any`. Unsupported
message shapes do not implement `ProtoJsonMessage`. Google's official suite
passes all 1476 proto3 binary and JSON cases and skips 1303 proto2 cases.
Proto2 schemas, Editions, and text format are outside the current supported
scope. The project has not had an external security review.
