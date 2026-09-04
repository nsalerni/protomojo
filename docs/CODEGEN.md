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
| enum | wrapper struct with `var value: Int32`, `comptime` constants, `name()`, and `from_name()` |
| message | `Optional[M]` |
| proto3 `optional` | `Optional[T]` |
| `repeated` | `List[T]` |
| `map<K, V>` | `Dict[K, V]` |
| `oneof` | member fields plus `*_case` |

Unknown fields are preserved. Nesting depth is limited to 100. Recursive
messages box self-referential fields as a 0-or-1 `List`. proto3 only; proto2
and editions are rejected. Enum wrappers keep proto3 open-enum semantics:
unknown numbers round-trip; `name()` is `None` for an unnamed value.

JSON mappings for generated messages are in [JSON.md](JSON.md).

## Services

When a `.proto` file declares a `service`, the plugin also emits stubs for
[grpc-mojo](https://github.com/nsalerni/grpc-mojo):

- `comptime <SERVICE>_<METHOD>_PATH` constants
- a `<Service>Client` wrapping `GrpcChannel`
  - unary: full request/response
  - server-streaming: `ServerStreamingCall[Resp]`
  - client-streaming: `ClientStreamingCall[Req, Resp]`
  - bidi: `BidiStreamingCall[Req, Resp]`
- `add_<service>_service[...](mut server: Server)` registering one
  compile-time handler per method kind
- `add_<service>_polling_service[...](mut server: PollingServer) raises`
  with the same handler parameters, for grpc-mojo's readiness-driven
  server. Registration can fail on a duplicate or malformed path.
