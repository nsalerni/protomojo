# protoc-gen-mojo

`tools/protoc-gen-mojo` turns `.proto` files into Mojo structs and, when
services are present, gRPC stubs for [grpc-mojo](https://github.com/nsalerni/grpc-mojo).

```sh
python3 -m grpc_tools.protoc \
  -I path/to/protos \
  --plugin=protoc-gen-mojo=tools/protoc-gen-mojo \
  --mojo_out=OUT_DIR \
  your.proto
```

One Mojo module is emitted per `.proto` file, including imported dependencies:
`foo/bar/baz.proto` → `baz_pb.mojo`. Put `OUT_DIR` on the include path.

## Type mapping

| proto3 | Mojo |
|---|---|
| `int32` / `int64` | `Int32` / `Int64` |
| `uint32` / `uint64` | `UInt32` / `UInt64` |
| `sint32` / `sint64` | `Int32` / `Int64` (ZigZag) |
| `fixed32` / `fixed64` | `UInt32` / `UInt64` |
| `sfixed32` / `sfixed64` | `Int32` / `Int64` |
| `float` / `double` | `Float32` / `Float64` |
| `bool` | `Bool` |
| `string` | `String` |
| `bytes` | `List[Byte]` |
| enum | `Int32` plus `comptime` constants |
| message | `Optional[M]` |
| proto3 `optional` | `Optional[T]` |
| `repeated` | `List[T]` |
| `map<K, V>` | `Dict[K, V]` |
| `oneof` | member fields plus `*_case` |

Unknown fields are preserved. Nesting depth is limited to 100. Recursive
messages box self-referential fields as a 0-or-1 `List`. proto3 only; proto2
and editions are rejected.

JSON mappings for generated messages are in [JSON.md](JSON.md).
