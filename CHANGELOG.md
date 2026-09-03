# Changelog

## Unreleased

## 0.4.1 - 2026-09-03

- Extends the JSON mutation runner to Timestamp, Duration, FieldMask,
  wrappers, and Struct/Value, still judged by Python `protobuf`.

- Extends binary wire fuzz with dedicated map, oneof, and `Any` seeds, and
  adds a JSON mutation runner for those shapes judged by Python `protobuf`.
  The JSON oracle requires a JSON object root so empty arrays and strings
  that Python `protobuf` treats as empty messages are not required accepts.

## 0.4.0 - 2026-08-27

- Generated proto3 enums are Equatable wrapper structs with a `value`
  field, `name()`, and `from_name()`, instead of a bare `Int32` plus
  constants. Unknown wire numbers still round-trip. This is a breaking
  change for generated message fields that were previously `Int32`.
- Generated gRPC streaming stubs return grpc-mojo's typed call objects
  (`ServerStreamingCall`, `ClientStreamingCall`, `BidiStreamingCall`)
  instead of documenting the raw stream-id flow.
- Documented that encode and decode are synchronous.
- `protoc-gen-mojo` rejects two `.proto` files that would emit the same
  Mojo module name. The plugin header matches current scope (imports,
  optional, streaming stubs).
- Added a roadmap that keeps proto2, editions, and text format as
  explicit non-goals.
- Rejects length-delimited protobuf fields larger than 64 MiB by default
  (`MAX_BYTES_FIELD`), configurable per `WireReader`.
- Shortened the README, added JSON and codegen guides, and added
  contributor, issue, and pull-request templates.

## 0.3.0 - 2026-08-25

- Rejects wire tags whose field number exceeds protobuf's 29-bit maximum
  instead of truncating the number.
- Adds deterministic wire mutation runs judged by Python `protobuf`. CI runs
  250 cases on each host, and the weekly job runs 20,000 cases from a fixed
  seed.
- Adds fresh code generation examples for binary messages and resolver-backed
  `Any`, plus a failure-safe official conformance badge.
- Adds strict proto3 JSON encode and decode support for generated messages
  made entirely of singular primitive fields. Unsupported message shapes
  remain ineligible at compile time.
- Checks JSON parsing and printing in both directions against Python
  `protobuf`, including malformed input and installed-package coverage.
- Adds proto3 JSON for singular enum fields, including aliases, negative
  values, and unknown numeric values. `ignore_unknown_fields` controls whether
  the parser rejects unknown enum names.
- Adds proto3 JSON for singular nested messages when every message in the
  field graph has a complete mapping.
- Adds proto3 JSON arrays for repeated scalar and enum fields. JSON null clears
  the field, while null array elements remain invalid outside repeated
  `google.protobuf.Value` fields.
- Adds proto3 JSON arrays for repeated ordinary message fields when the child
  type has a complete mapping.
- Adds proto3 JSON objects for string-key maps with scalar or enum values.
  Duplicate keys and null entry values are rejected outside maps whose value
  type is `google.protobuf.Value`.
- Adds every protobuf integer and boolean map-key type to the JSON mapping.
  Keys print as canonical JSON object names and parse with their protobuf
  range checks.
- Adds ordinary message values to the JSON map mapping when the child message
  has a complete mapping.
- Adds proto3 JSON for oneof members. Selected default values are printed,
  null leaves ordinary oneof members unset, and multiple selected members are
  rejected.
- Adds proto3 JSON for optional fields. Present default values are printed and
  null clears explicit presence for ordinary optional fields. Optional
  `google.protobuf.Value` and `NullValue` preserve presence for null.
- Adds the standard `{}` JSON mapping for `google.protobuf.Empty`, both as a
  direct value and as a message field.
- Adds the scalar JSON mapping for all nine protobuf wrapper types. Wrapper
  fields preserve present defaults and treat `null` as absent.
- Preserves negative zero when generated float and double fields serialize to
  the binary wire format or proto3 JSON.
- Adds the RFC 3339 JSON mapping for `google.protobuf.Timestamp`, including UTC
  normalization, numeric offsets, nanosecond precision, and range checks.
- Adds the signed decimal JSON mapping for `google.protobuf.Duration`, with
  canonical fractional output and strict sign and range checks.
- Adds the comma-separated lowerCamelCase JSON mapping for
  `google.protobuf.FieldMask`, with strict checks for case conversion.
- Adds proto3 JSON for recursive message graphs when every referenced type has
  a complete mapping, including the standard 100-level parse limit.
- Adds the standard JSON mappings for `google.protobuf.Struct`, `Value`,
  `ListValue`, and `NullValue`, including nested values, null Value entries,
  null oneofs, and optional NullValue presence.
- Adds ordinary message JSON mappings for `google.protobuf.SourceContext` and
  `Mixin`.
- Adds resolver-backed JSON support for `google.protobuf.Any`. The generator
  emits static dispatch for the message types in each protoc request.
- Uses a deterministic SHA-256 filename for multi-target and overlong JSON
  resolvers. Ordinary single-target names stay unchanged.
- Runs the official protobuf proto3 binary and JSON conformance groups with
  1476 cases passing and no unexpected failures. The runner skips 1303 proto2
  cases.
- Requires the generated compliance report to contain the exact 92 registered
  checks before Markdown, HTML, or the badge can report success.
- Preserves the complete outer map field when an entry contains an unknown
  inner field, without inserting a partial map item.

## 0.2.0 - 2026-08-20

- Packages the Mojo 1.0 `proto` runtime and `protoc-gen-mojo` together so
  installed environments can discover the plugin, generate Mojo sources,
  and compile them without a source checkout.
- Runs unit tests, benchmark smoke checks, and Google protobuf conformance
  on macOS and Linux. The release gate requires exactly 698 binary
  wire-format cases to pass with no unexpected failures.

## 0.1.0 - 2026-08-19

Initial release.

- Proto3 binary wire format: `WireWriter` / `WireReader` with varints,
  zigzag, fixed fields, length-delimited coding, unknown-field capture,
  nesting-depth limit, and hardened bounds checks on hostile input.
- `ProtoMessage` trait with `encode[M]` / `decode[M]`.
- `protoc-gen-mojo`: proto3 messages (scalars, repeated packed/unpacked,
  maps, oneofs, `optional` presence, recursion via boxing), cross-file
  imports, unknown-field preservation, and gRPC service stubs.
- Google protobuf conformance suite: 698/698 binary tests pass; randomized
  differential testing vs Python `protobuf`; golden-byte pinned behavior.
