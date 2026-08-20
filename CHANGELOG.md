# Changelog

## 0.1.0 — 2026-08-19

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
