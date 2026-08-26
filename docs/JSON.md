# proto3 JSON mapping

Generated messages implement `ProtoJsonMessage` when every field in the type
graph has a mapping. Unsupported shapes fail at compile time.

| proto3 | JSON |
|---|---|
| Integers, bool, string, bytes | Standard proto3 JSON (`int64`/`uint64` as strings) |
| `float` / `double` | Numbers; negative zero is preserved |
| Enum | Name on the wire; unknown numeric values kept; aliases print the first declared name |
| Message | JSON object |
| `repeated` | JSON array; JSON `null` clears the field |
| `map` | JSON object; keys use canonical JSON names |
| `oneof` | Selected member, including default values |
| proto3 `optional` | Presence preserved; `null` clears ordinary optional fields |
| `google.protobuf.Empty` | `{}` |
| Scalar wrappers | Standard scalar JSON; presence kept for defaults |
| `Timestamp` | RFC 3339 UTC, shortest exact 0/3/6/9 fractional digits |
| `Duration` | Signed seconds with the same fractional rules |
| `FieldMask` | Comma-separated lowerCamelCase paths |
| `Struct` / `Value` / `ListValue` / `NullValue` | JSON object / value / array / `null` |
| `Any` | Static resolver generated with the message modules |

`Any` parsing and printing (other than empty `{}`) needs the generated
resolver. The resolver only looks at the message name after the final slash
in a type URL; it never fetches the URL.

```mojo
from proto import JsonParseOptions, decode_json
from vectors_pb_json_resolver import json_type_resolver

var options = JsonParseOptions(type_resolver=json_type_resolver())
var value = decode_json[Any](
    '{"@type":"type.googleapis.com/grpcmojo.test.EchoRequest",'
    '"message":"hello"}',
    options=options,
)
```

Type mapping for generated structs is in [CODEGEN.md](CODEGEN.md). Conformance
results are in [COMPLIANCE.md](../COMPLIANCE.md).
