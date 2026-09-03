# Roadmap

Shipped work lives in [CHANGELOG.md](CHANGELOG.md).

## Open

Nothing currently in scope is waiting on a local API. Well-known JSON
fuzz for Timestamp, Duration, FieldMask, wrappers, and Struct/Value
shipped in 0.4.1. `add_<service>_polling_service` shipped in 0.4.2.

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
