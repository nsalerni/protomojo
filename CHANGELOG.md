# Changelog

## Unreleased

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
  the field, while null array elements remain invalid.
- Adds proto3 JSON arrays for repeated ordinary message fields when the child
  type has a complete mapping.
- Adds proto3 JSON objects for string-key maps with scalar or enum values.
  Duplicate keys and null entry values are rejected.
- Adds every protobuf integer and boolean map-key type to the JSON mapping.
  Keys print as canonical JSON object names and parse with their protobuf
  range checks.
- Adds ordinary message values to the JSON map mapping when the child message
  has a complete mapping.
- Adds proto3 JSON for oneof members. Selected default values are printed,
  null leaves a oneof unset, and multiple non-null members are rejected.
- Adds proto3 JSON for optional fields. Present default values are printed and
  null clears explicit presence.
- Adds the standard `{}` JSON mapping for `google.protobuf.Empty`, both as a
  direct value and as a message field.
- Requires the generated compliance report to contain the exact 55 registered
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
