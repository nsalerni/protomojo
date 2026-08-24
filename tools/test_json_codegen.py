#!/usr/bin/env python3
"""Check JSON code generation eligibility and checked-in freshness."""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import grpc_tools


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "tools" / "protoc-gen-mojo"


def generate(proto: Path, output: Path, *includes: Path) -> Path:
    command = [sys.executable, "-m", "grpc_tools.protoc"]
    command.extend(f"-I{path}" for path in includes)
    command.extend(
        [
            f"--plugin=protoc-gen-mojo={PLUGIN}",
            f"--mojo_out={output}",
            str(proto),
        ]
    )
    subprocess.run(command, cwd=ROOT, check=True)
    return output / (proto.stem + "_pb.mojo")


def has_json_trait(source: str, name: str) -> bool:
    match = re.search(rf"^struct {name}\(([^)]*)\):", source, re.MULTILINE)
    if match is None:
        raise AssertionError(f"missing generated struct {name}")
    return "ProtoJsonMessage" in match.group(1)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="protomojo-json-codegen-") as temp:
        output = Path(temp)
        generated = generate(ROOT / "test" / "vectors.proto", output, ROOT / "test")
        source = generated.read_text()
        assert source == (ROOT / "test" / "vectors_pb.mojo").read_text()
        assert has_json_trait(source, "Scalars")
        assert has_json_trait(source, "EchoRequest")
        assert not has_json_trait(source, "Nested")
        assert not has_json_trait(source, "Tree")

        shape_proto = output / "json_shapes.proto"
        shape_proto.write_text(
            'syntax = "proto3";\n'
            'import "google/protobuf/source_context.proto";\n'
            'import "google/protobuf/timestamp.proto";\n'
            'enum Choice { CHOICE_UNSPECIFIED = 0; CHOICE_ONE = 1; }\n'
            'message Flat { int32 number = 1; string text = 2; }\n'
            'message Child { int32 value = 1; }\n'
            'message HasEnum { Choice value = 1; }\n'
            'message HasRepeated { repeated int32 values = 1; }\n'
            'message HasMap { map<string, int32> values = 1; }\n'
            'message HasOneof { oneof selection { int32 number = 1; string text = 2; } }\n'
            'message HasMessage { Child value = 1; }\n'
            'message HasOptional { optional int32 value = 1; }\n'
            'message HasSourceContext { google.protobuf.SourceContext value = 1; }\n'
            'message HasTimestamp { google.protobuf.Timestamp value = 1; }\n'
        )
        protobuf_include = Path(grpc_tools.__file__).parent / "_proto"
        generated = generate(shape_proto, output, output, protobuf_include)
        source = generated.read_text()
        assert has_json_trait(source, "Flat")
        assert has_json_trait(source, "Child")
        assert not has_json_trait(source, "HasEnum")
        assert not has_json_trait(source, "HasRepeated")
        assert not has_json_trait(source, "HasMap")
        assert not has_json_trait(source, "HasOneof")
        assert not has_json_trait(source, "HasMessage")
        assert not has_json_trait(source, "HasOptional")
        assert not has_json_trait(source, "HasSourceContext")
        assert not has_json_trait(source, "HasTimestamp")

        source_context = (output / "source_context_pb.mojo").read_text()
        assert not has_json_trait(source_context, "SourceContext")
        timestamp = (output / "timestamp_pb.mojo").read_text()
        assert not has_json_trait(timestamp, "Timestamp")

    print("test_json_codegen: all tests passed")


if __name__ == "__main__":
    main()
