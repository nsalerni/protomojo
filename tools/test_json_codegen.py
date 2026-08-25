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
        assert has_json_trait(source, "JsonRepeated")
        assert has_json_trait(source, "JsonRepeatedMessages")
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
            'message ImportedChild { int32 value = 1; }\n'
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
            'message HasRepeatedMessage { repeated Child values = 1; }\n'
            'message HasRepeatedParent { HasRepeated value = 1; }\n'
            'message HasMap { map<string, int32> values = 1; }\n'
            'message HasOneof { oneof selection { int32 number = 1; string text = 2; } }\n'
            'message HasMessage { Child value = 1; }\n'
            'message HasNestedMessage { HasMessage value = 1; }\n'
            'message HasImportedMessage { ImportedChild value = 1; }\n'
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
        assert has_json_trait(source, "HasRepeated")
        assert has_json_trait(source, "HasRepeatedMessage")
        assert has_json_trait(source, "HasRepeatedParent")
        assert not has_json_trait(source, "HasMap")
        assert not has_json_trait(source, "HasOneof")
        assert has_json_trait(source, "HasMessage")
        assert has_json_trait(source, "HasNestedMessage")
        assert has_json_trait(source, "HasImportedMessage")
        assert not has_json_trait(source, "HasOptional")
        assert not has_json_trait(source, "HasSourceContext")
        assert not has_json_trait(source, "HasTimestamp")

        source_context = (output / "source_context_pb.mojo").read_text()
        assert not has_json_trait(source_context, "SourceContext")
        timestamp = (output / "timestamp_pb.mojo").read_text()
        assert not has_json_trait(timestamp, "Timestamp")

        probe = output / "enum_json_probe.mojo"
        probe.write_text(
            "from std.testing import assert_equal, assert_true\n"
            "from proto import (\n"
            "    JsonParseOptions,\n"
            "    JsonPrintOptions,\n"
            "    decode_json,\n"
            "    encode_json,\n"
            ")\n"
            "from json_enum_pb import ImportedChild, ImportedChoice\n"
            "from json_shapes_pb import (\n"
            "    Choice,\n"
            "    Child,\n"
            "    HasEnum,\n"
            "    HasImportedEnum,\n"
            "    HasImportedMessage,\n"
            "    HasMessage,\n"
            "    HasNestedMessage,\n"
            "    HasNestedEnum,\n"
            "    HasNestedEnum_NestedChoice,\n"
            "    HasRepeated,\n"
            "    HasRepeatedMessage,\n"
            "    HasRepeatedParent,\n"
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
            "\n"
            "    var parent = HasMessage()\n"
            "    var child = Child()\n"
            "    child.value = 7\n"
            "    parent.value = child^\n"
            "    assert_equal(encode_json(parent), "
            "'{\\\"value\\\":{\\\"value\\\":7}}')\n"
            "    var decoded = decode_json[HasMessage]("
            "'{\\\"value\\\":{\\\"value\\\":9}}')\n"
            "    assert_true(decoded.value)\n"
            "    assert_equal(decoded.value.value().value, 9)\n"
            "    var cleared = decode_json[HasMessage]("
            "'{\\\"value\\\":null}')\n"
            "    assert_true(not cleared.value)\n"
            "    var empty_child = Child()\n"
            "    var present_empty = HasMessage()\n"
            "    present_empty.value = empty_child^\n"
            "    assert_equal(encode_json(present_empty), "
            "'{\\\"value\\\":{}}')\n"
            "    var decoded_empty = decode_json[HasMessage]("
            "'{\\\"value\\\":{}}')\n"
            "    assert_true(decoded_empty.value)\n"
            "    var print_defaults = JsonPrintOptions("
            "always_print_fields_with_no_presence=True)\n"
            "    assert_equal(encode_json(HasMessage(), "
            "options=print_defaults), '{}')\n"
            "\n"
            "    var imported_child = ImportedChild()\n"
            "    imported_child.value = 11\n"
            "    var imported_parent = HasImportedMessage()\n"
            "    imported_parent.value = imported_child^\n"
            "    assert_equal(encode_json(imported_parent), "
            "'{\\\"value\\\":{\\\"value\\\":11}}')\n"
            "\n"
            "    var deep = decode_json[HasNestedMessage]("
            "'{\\\"value\\\":{\\\"value\\\":{\\\"value\\\":13}}}')\n"
            "    assert_true(deep.value)\n"
            "    assert_true(deep.value.value().value)\n"
            "    assert_equal(deep.value.value().value.value().value, 13)\n"
            "\n"
            "    var shallow = JsonParseOptions(max_depth=1)\n"
            "    var depth_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[HasMessage]("
            "'{\\\"value\\\":{}}', options=shallow)\n"
            "    except:\n"
            "        depth_rejected = True\n"
            "    assert_true(depth_rejected)\n"
            "\n"
            "    var repeated = HasRepeated()\n"
            "    repeated.values.append(1)\n"
            "    repeated.values.append(-2)\n"
            "    assert_equal(encode_json(repeated), "
            "'{\\\"values\\\":[1,-2]}')\n"
            "    var decoded_repeated = decode_json[HasRepeated]("
            "'{\\\"values\\\":[3,4]}')\n"
            "    assert_equal(len(decoded_repeated.values), 2)\n"
            "    assert_equal(decoded_repeated.values[0], 3)\n"
            "    assert_equal(decoded_repeated.values[1], 4)\n"
            "    var cleared_repeated = decode_json[HasRepeated]("
            "'{\\\"values\\\":null}')\n"
            "    assert_equal(len(cleared_repeated.values), 0)\n"
            "    assert_equal(encode_json(HasRepeated(), "
            "options=print_defaults), '{\\\"values\\\":[]}')\n"
            "    var null_element_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[HasRepeated]("
            "'{\\\"values\\\":[null]}')\n"
            "    except:\n"
            "        null_element_rejected = True\n"
            "    assert_true(null_element_rejected)\n"
            "    var array_depth_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[HasRepeated]("
            "'{\\\"values\\\":[]}', options=shallow)\n"
            "    except:\n"
            "        array_depth_rejected = True\n"
            "    assert_true(array_depth_rejected)\n"
            "    var repeated_parent = decode_json[HasRepeatedParent]("
            "'{\\\"value\\\":{\\\"values\\\":[5,6]}}')\n"
            "    assert_true(repeated_parent.value)\n"
            "    assert_equal(repeated_parent.value.value().values[1], 6)\n"
            "    var nested_array_depth = JsonParseOptions(max_depth=2)\n"
            "    var nested_array_depth_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[HasRepeatedParent]("
            "'{\\\"value\\\":{\\\"values\\\":[]}}', "
            "options=nested_array_depth)\n"
            "    except:\n"
            "        nested_array_depth_rejected = True\n"
            "    assert_true(nested_array_depth_rejected)\n"
            "\n"
            "    var repeated_message = HasRepeatedMessage()\n"
            "    var repeated_child = Child()\n"
            "    repeated_child.value = 17\n"
            "    repeated_message.values.append(repeated_child^)\n"
            "    assert_equal(encode_json(repeated_message), "
            "'{\\\"values\\\":[{\\\"value\\\":17}]}')\n"
            "    var decoded_messages = decode_json[HasRepeatedMessage]("
            "'{\\\"values\\\":[{}, {\\\"value\\\":19}]}')\n"
            "    assert_equal(len(decoded_messages.values), 2)\n"
            "    assert_equal(decoded_messages.values[1].value, 19)\n"
            "    var message_depth = JsonParseOptions(max_depth=2)\n"
            "    var message_depth_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[HasRepeatedMessage]("
            "'{\\\"values\\\":[{}]}', options=message_depth)\n"
            "    except:\n"
            "        message_depth_rejected = True\n"
            "    assert_true(message_depth_rejected)\n"
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
