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
        enum_proto = output / "json_enum.proto"
        enum_proto.write_text(
            'syntax = "proto3";\n'
            'enum ImportedChoice {\n'
            '  IMPORTED_UNSPECIFIED = 0;\n'
            '  IMPORTED_ONE = 1;\n'
            '  IMPORTED_MIN = -2147483648;\n'
            '  IMPORTED_MAX = 2147483647;\n'
            '}\n'
        )
        shape_proto.write_text(
            'syntax = "proto3";\n'
            'import "json_enum.proto";\n'
            'import "google/protobuf/source_context.proto";\n'
            'import "google/protobuf/timestamp.proto";\n'
            'enum Choice {\n'
            '  CHOICE_UNSPECIFIED = 0;\n'
            '  CHOICE_ONE = 1;\n'
            '  CHOICE_MIN = -2147483648;\n'
            '  CHOICE_MAX = 2147483647;\n'
            '}\n'
            'message Flat { int32 number = 1; string text = 2; }\n'
            'message Child { int32 value = 1; }\n'
            'message HasEnum { Choice value = 1; }\n'
            'message HasNestedEnum {\n'
            '  enum NestedChoice {\n'
            '    NESTED_UNSPECIFIED = 0;\n'
            '    NESTED_ONE = 1;\n'
            '    NESTED_MIN = -2147483648;\n'
            '    NESTED_MAX = 2147483647;\n'
            '  }\n'
            '  NestedChoice value = 1;\n'
            '}\n'
            'message HasImportedEnum { ImportedChoice value = 1; }\n'
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
        assert has_json_trait(source, "HasEnum")
        assert has_json_trait(source, "HasNestedEnum")
        assert has_json_trait(source, "HasImportedEnum")
        assert 'writer.string_value("CHOICE_ONE")' in source
        assert 'enum_name.value() == "CHOICE_ONE"' in source
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

        probe = output / "enum_json_probe.mojo"
        probe.write_text(
            "from std.testing import assert_equal\n"
            "from proto import decode_json, encode_json\n"
            "from json_enum_pb import ImportedChoice\n"
            "from json_shapes_pb import (\n"
            "    Choice,\n"
            "    HasEnum,\n"
            "    HasImportedEnum,\n"
            "    HasNestedEnum,\n"
            "    HasNestedEnum_NestedChoice,\n"
            ")\n"
            "\n"
            "def main() raises:\n"
            "    var local = HasEnum()\n"
            "    local.value = Choice.CHOICE_MIN\n"
            "    assert_equal(encode_json(local), "
            "'{\\\"value\\\":\\\"CHOICE_MIN\\\"}')\n"
            "    var local_max = decode_json[HasEnum]("
            "'{\\\"value\\\":\\\"CHOICE_MAX\\\"}')\n"
            "    assert_equal(local_max.value, Choice.CHOICE_MAX)\n"
            "\n"
            "    var nested = HasNestedEnum()\n"
            "    nested.value = HasNestedEnum_NestedChoice.NESTED_MAX\n"
            "    assert_equal(encode_json(nested), "
            "'{\\\"value\\\":\\\"NESTED_MAX\\\"}')\n"
            "    var nested_min = decode_json[HasNestedEnum]("
            "'{\\\"value\\\":\\\"NESTED_MIN\\\"}')\n"
            "    assert_equal(\n"
            "        nested_min.value, HasNestedEnum_NestedChoice.NESTED_MIN\n"
            "    )\n"
            "\n"
            "    var imported = HasImportedEnum()\n"
            "    imported.value = ImportedChoice.IMPORTED_MIN\n"
            "    assert_equal(encode_json(imported), "
            "'{\\\"value\\\":\\\"IMPORTED_MIN\\\"}')\n"
            "    var imported_max = decode_json[HasImportedEnum]("
            "'{\\\"value\\\":\\\"IMPORTED_MAX\\\"}')\n"
            "    assert_equal(imported_max.value, ImportedChoice.IMPORTED_MAX)\n"
        )
        subprocess.run(
            [
                "mojo",
                "run",
                "-I",
                str(ROOT / "src"),
                "-I",
                str(output),
                str(probe),
            ],
            cwd=ROOT,
            check=True,
        )

    print("test_json_codegen: all tests passed")


if __name__ == "__main__":
    main()
