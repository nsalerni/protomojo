# Examples

`pixi run example` regenerates Mojo from the `.proto` files in a temporary
directory, then runs both programs.

| File | What it shows |
|---|---|
| [address_book.proto](address_book.proto) / [codegen_roundtrip.mojo](codegen_roundtrip.mojo) | Scalar, repeated, map, and nested fields |
| [protojson_any.proto](protojson_any.proto) / [protojson_any.mojo](protojson_any.mojo) | Pack, print, parse, and unpack `Any` |

```sh
pixi run example
```
