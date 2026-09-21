# Protobuf without gRPC

protomojo is the proto3 runtime for any Mojo program, not only gRPC.

```sh
pixi add protomojo
```

`protoc-gen-mojo` is on `PATH`. Generate a module from a `.proto`:

```sh
python3 -m grpc_tools.protoc -I proto \
  --plugin=protoc-gen-mojo=$(command -v protoc-gen-mojo) \
  --mojo_out=src proto/addressbook.proto
```

```mojo
from proto import decode, encode

var book = AddressBook()
var wire = encode(book)
var parsed = decode[AddressBook](Span(wire))
```

JSON, when every field in the type graph has a mapping:

```mojo
from proto import decode_json, encode_json

var text = encode_json(book)
var parsed = decode_json[AddressBook](text)
```

gRPC stubs are optional: they are emitted only when the `.proto` declares
a `service`, and they import [grpc-mojo](https://github.com/nsalerni/grpc-mojo)
at the generated-code boundary. The `proto` runtime itself depends only
on the Mojo standard library.

Out of scope: proto2, editions, and text format.
