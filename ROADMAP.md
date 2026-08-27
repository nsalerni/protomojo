# Roadmap

Shipped work lives in [CHANGELOG.md](CHANGELOG.md).

## Open

These are not blocked on Mojo 1.0 or another package:

- Broader fuzz of maps, oneof, `Any`, and JSON. Binary wire fuzz already
  runs in CI; the remaining shapes need the same seeded differential against
  Python `protobuf`.

Typed enum structs shipped in 0.4.0: generated enums are Equatable
wrappers with `value`, `name()`, and `from_name()`. Unknown proto3
numbers still round-trip. grpc-mojo can regenerate stubs that contain
enums after pinning this tag; `echo.proto` has none.

## Blocked

Nothing currently in scope is waiting on a Mojo language feature. Encode
and decode are synchronous by design.

## Non-goals

These stay out on purpose:

- proto2 syntax
- Protobuf Editions
- Text format
- Extensions
- Dynamic `google.protobuf.Any` packing unless a consumer appears
