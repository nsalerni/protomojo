# Roadmap

Shipped work lives in [CHANGELOG.md](CHANGELOG.md).

## Open

- Codegen collision is now an error when two `.proto` files share a
  basename; remaining honesty work is typed enum structs instead of
  `Int32` plus constants
- Broader fuzz of maps, oneof, `Any`, and JSON (binary wire fuzz already
  runs in CI)

## Non-goals

These stay out on purpose:

- proto2 syntax
- Protobuf Editions
- Text format
- Extensions
- Dynamic `google.protobuf.Any` packing unless a consumer appears
