#!/usr/bin/env python3
"""Keyword and builtin proto names must compile and match Python protobuf."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from google.protobuf import json_format


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "tools" / "protoc-gen-mojo"

# The oneof uses the highest field numbers. Generated encode writes oneof
# members after other fields, and Python writes field-number order.
PROTO = """syntax = "proto3";

package reserved;

message Error {
  string detail = 1;
}

message String {
  int32 value = 1;
}

message Reserved {
  string from = 1;
  string class = 2;
  string match = 3;
  Error error = 4;
  oneof try {
    string async = 5;
    int32 await = 6;
  }
}

service ReservedApi {
  rpc Import(Reserved) returns (Error);
}
"""

DRIVER = """from reserved_names_pb import Error_, Reserved
from proto import decode, decode_json, encode, encode_json


def dump(label: String, data: List[Byte]):
    var line = label
    for b in data:
        line += " "
        line += String(Int(b))
    print(line)


def main() raises:
    var message = Reserved()
    message.from_ = "a"
    message.class_ = "b"
    message.match_ = "c"
    message.async_ = "d"
    message.try__case = 5
    var err = Error_()
    err.detail = "e"
    message.error = err^

    var wire = encode(message)
    var round_trip = encode(decode[Reserved](Span(wire)))
    var text = encode_json(message)
    var parsed = decode_json[Reserved](text)
    var json_round = encode(parsed)

    dump("WIRE", wire)
    dump("ROUND", round_trip)
    dump("JSONROUND", json_round)
    print("JSON " + text)
"""

# The generated service imports grpc, which this repo does not ship.
# Empty structs let that import parse. A keyword method name still fails here.
GRPC_STUB = """struct BidiStreamingCall:
    pass


struct ClientStreamingCall:
    pass


struct GrpcChannel:
    pass


struct PollingServer:
    pass


struct Server:
    pass


struct ServerCall:
    pass


struct ServerContext:
    pass


struct ServerStreamingCall:
    pass


struct ReflectionRegistry:
    pass
"""

EXPECTED_JSON = (
    '{"from":"a","class":"b","match":"c","error":{"detail":"e"},"async":"d"}'
)


def parse_bytes(line: str, label: str) -> bytes:
    parts = line.split()
    if not parts or parts[0] != label:
        raise AssertionError(f"missing {label} line: {line!r}")
    return bytes(int(part) for part in parts[1:])


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="protomojo-reserved-") as temp:
        root = Path(temp)
        proto = root / "reserved_names.proto"
        proto.write_text(PROTO)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"-I{root}",
                f"--python_out={root}",
                f"--plugin=protoc-gen-mojo={PLUGIN}",
                f"--mojo_out={root}",
                str(proto),
            ],
            cwd=ROOT,
            check=True,
        )
        (root / "grpc.mojo").write_text(GRPC_STUB)
        (root / "driver.mojo").write_text(DRIVER)
        compiled = subprocess.run(
            [
                "mojo",
                "build",
                str(root / "driver.mojo"),
                "-I",
                str(ROOT / "src"),
                "-I",
                str(root),
                "-o",
                str(root / "driver"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if compiled.returncode != 0:
            sys.stderr.write(compiled.stderr)
            sys.stderr.write(compiled.stdout)
            raise SystemExit(compiled.returncode)
        ran = subprocess.run(
            [str(root / "driver")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        sys.path.insert(0, str(root))
        import reserved_names_pb2  # noqa: E402

        lines = [line for line in ran.stdout.splitlines() if line]
        wire = parse_bytes(lines[0], "WIRE")
        round_trip = parse_bytes(lines[1], "ROUND")
        json_round = parse_bytes(lines[2], "JSONROUND")
        if not lines[3].startswith("JSON "):
            raise AssertionError(f"missing JSON line: {lines[3]!r}")
        mojo_json = lines[3][len("JSON ") :]

        expected = reserved_names_pb2.Reserved()
        json_format.ParseDict(
            {
                "from": "a",
                "class": "b",
                "match": "c",
                "error": {"detail": "e"},
                "async": "d",
            },
            expected,
        )
        python_bytes = expected.SerializeToString()
        python_json = json_format.MessageToJson(
            expected, indent=None, ensure_ascii=True
        )

    assert wire == python_bytes, (wire.hex(), python_bytes.hex())
    assert round_trip == python_bytes
    assert json_round == python_bytes
    assert mojo_json == EXPECTED_JSON
    assert json.loads(mojo_json) == json.loads(python_json)
    print("test_reserved_names: all tests passed")


if __name__ == "__main__":
    main()
