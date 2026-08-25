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
        protobuf_include = Path(grpc_tools.__file__).parent / "_proto"
        generated_struct = generate(
            protobuf_include / "google" / "protobuf" / "struct.proto",
            output,
            protobuf_include,
        )
        struct_source = generated_struct.read_text()
        assert struct_source == (ROOT / "test" / "struct_pb.mojo").read_text()
        assert has_json_trait(struct_source, "Struct")
        assert has_json_trait(struct_source, "Value")
        assert has_json_trait(struct_source, "ListValue")
        generated = generate(ROOT / "test" / "vectors.proto", output, ROOT / "test")
        source = generated.read_text()
        assert source == (ROOT / "test" / "vectors_pb.mojo").read_text()
        assert has_json_trait(source, "Scalars")
        assert has_json_trait(source, "EchoRequest")
        assert has_json_trait(source, "JsonRepeated")
        assert has_json_trait(source, "JsonRepeatedMessages")
        assert has_json_trait(source, "Nested")
        assert has_json_trait(source, "Tree")
        assert has_json_trait(source, "JsonStructValues")

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
            'import "google/protobuf/duration.proto";\n'
            'import "google/protobuf/empty.proto";\n'
            'import "google/protobuf/field_mask.proto";\n'
            'import "google/protobuf/source_context.proto";\n'
            'import "google/protobuf/struct.proto";\n'
            'import "google/protobuf/timestamp.proto";\n'
            'import "google/protobuf/wrappers.proto";\n'
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
            'message HasIntKeyMap { map<int32, int32> values = 1; }\n'
            'message HasMessageMap { map<string, Child> values = 1; }\n'
            'message HasRecursiveMap { map<string, HasRecursiveMap> values = 1; }\n'
            'message HasOneof { oneof selection { int32 number = 1; string text = 2; } }\n'
            'message HasMessage { Child value = 1; }\n'
            'message HasNestedMessage { HasMessage value = 1; }\n'
            'message HasImportedMessage { ImportedChild value = 1; }\n'
            'message HasOptional { optional int32 value = 1; }\n'
            'message HasDuration { google.protobuf.Duration value = 1; }\n'
            'message HasEmpty { google.protobuf.Empty value = 1; }\n'
            'message HasFieldMask { google.protobuf.FieldMask value = 1; }\n'
            'message HasSourceContext { google.protobuf.SourceContext value = 1; }\n'
            'message HasTimestamp { google.protobuf.Timestamp value = 1; }\n'
            'message HasStruct { google.protobuf.Struct value = 1; }\n'
            'message HasValue { google.protobuf.Value value = 1; }\n'
            'message HasListValue { google.protobuf.ListValue value = 1; }\n'
            'message HasOptionalNull { optional google.protobuf.NullValue value = 1; }\n'
            'message HasValueMap { map<string, google.protobuf.Value> values = 1; }\n'
            'message HasValueOneof { oneof selection { google.protobuf.Value value = 1; string text = 2; } }\n'
            'message HasOptionalValue { google.protobuf.Value value = 1; }\n'
            'message HasRepeatedNull { repeated google.protobuf.NullValue values = 1; }\n'
            'message HasNullMap { map<string, google.protobuf.NullValue> values = 1; }\n'
            'message HasWrapper { google.protobuf.Int32Value value = 1; }\n'
        )
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
        assert has_json_trait(source, "HasMap")
        assert has_json_trait(source, "HasIntKeyMap")
        assert has_json_trait(source, "HasMessageMap")
        assert has_json_trait(source, "HasRecursiveMap")
        assert has_json_trait(source, "HasOneof")
        assert has_json_trait(source, "HasMessage")
        assert has_json_trait(source, "HasNestedMessage")
        assert has_json_trait(source, "HasImportedMessage")
        assert has_json_trait(source, "HasOptional")
        assert has_json_trait(source, "HasDuration")
        assert has_json_trait(source, "HasEmpty")
        assert has_json_trait(source, "HasFieldMask")
        assert not has_json_trait(source, "HasSourceContext")
        assert has_json_trait(source, "HasTimestamp")
        assert has_json_trait(source, "HasStruct")
        assert has_json_trait(source, "HasValue")
        assert has_json_trait(source, "HasListValue")
        assert has_json_trait(source, "HasOptionalNull")
        assert has_json_trait(source, "HasValueMap")
        assert has_json_trait(source, "HasValueOneof")
        assert has_json_trait(source, "HasOptionalValue")
        assert has_json_trait(source, "HasRepeatedNull")
        assert has_json_trait(source, "HasNullMap")
        assert has_json_trait(source, "HasWrapper")

        source_context = (output / "source_context_pb.mojo").read_text()
        assert not has_json_trait(source_context, "SourceContext")
        timestamp = (output / "timestamp_pb.mojo").read_text()
        assert has_json_trait(timestamp, "Timestamp")
        duration = (output / "duration_pb.mojo").read_text()
        assert has_json_trait(duration, "Duration")
        empty = (output / "empty_pb.mojo").read_text()
        assert has_json_trait(empty, "Empty")
        field_mask = (output / "field_mask_pb.mojo").read_text()
        assert has_json_trait(field_mask, "FieldMask")
        wrappers = (output / "wrappers_pb.mojo").read_text()
        assert has_json_trait(wrappers, "Int32Value")
        assert has_json_trait(wrappers, "BytesValue")

        probe = output / "enum_json_probe.mojo"
        probe.write_text(
            "from std.testing import assert_equal, assert_true\n"
            "from proto import (\n"
            "    JsonParseOptions,\n"
            "    JsonPrintOptions,\n"
            "    ProtoJsonReader,\n"
            "    decode_json,\n"
            "    encode_json,\n"
            ")\n"
            "from json_enum_pb import ImportedChild, ImportedChoice\n"
            "from duration_pb import Duration\n"
            "from empty_pb import Empty\n"
            "from field_mask_pb import FieldMask\n"
            "from struct_pb import ListValue, Struct, Value\n"
            "from timestamp_pb import Timestamp\n"
            "from wrappers_pb import Int32Value\n"
            "from vectors_pb import Tree\n"
            "from json_shapes_pb import (\n"
            "    Choice,\n"
            "    Child,\n"
            "    HasDuration,\n"
            "    HasEnum,\n"
            "    HasEmpty,\n"
            "    HasFieldMask,\n"
            "    HasImportedEnum,\n"
            "    HasImportedMessage,\n"
            "    HasIntKeyMap,\n"
            "    HasMap,\n"
            "    HasMessageMap,\n"
            "    HasMessage,\n"
            "    HasNestedMessage,\n"
            "    HasNestedEnum,\n"
            "    HasNestedEnum_NestedChoice,\n"
            "    HasOneof,\n"
            "    HasOptional,\n"
            "    HasTimestamp,\n"
            "    HasStruct,\n"
            "    HasValue,\n"
            "    HasListValue,\n"
            "    HasOptionalNull,\n"
            "    HasValueMap,\n"
            "    HasValueOneof,\n"
            "    HasOptionalValue,\n"
            "    HasRepeatedNull,\n"
            "    HasNullMap,\n"
            "    HasWrapper,\n"
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
            "\n"
            "    var string_map = HasMap()\n"
            "    string_map.values[String(\"a\\\"b\")] = 17\n"
            "    assert_equal(encode_json(string_map), "
            "'{\\\"values\\\":{\\\"a\\\\\\\"b\\\":17}}')\n"
            "    var decoded_map = decode_json[HasMap]("
            "'{\\\"values\\\":{\\\"left\\\":1,\\\"right\\\":2}}')\n"
            "    assert_equal(decoded_map.values[String(\"left\")], 1)\n"
            "    assert_equal(decoded_map.values[String(\"right\")], 2)\n"
            "    var cleared_map = decode_json[HasMap]("
            "'{\\\"values\\\":null}')\n"
            "    assert_equal(len(cleared_map.values), 0)\n"
            "    var null_map_value_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[HasMap]("
            "'{\\\"values\\\":{\\\"bad\\\":null}}')\n"
            "    except:\n"
            "        null_map_value_rejected = True\n"
            "    assert_true(null_map_value_rejected)\n"
            "    var duplicate_map_key_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[HasMap]("
            "'{\\\"values\\\":{\\\"same\\\":1,\\\"same\\\":2}}')\n"
            "    except:\n"
            "        duplicate_map_key_rejected = True\n"
            "    assert_true(duplicate_map_key_rejected)\n"
            "    var map_depth_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[HasMap]("
            "'{\\\"values\\\":{}}', options=shallow)\n"
            "    except:\n"
            "        map_depth_rejected = True\n"
            "    assert_true(map_depth_rejected)\n"
            "\n"
            "    var int_key_map = HasIntKeyMap()\n"
            "    int_key_map.values[7] = 9\n"
            "    assert_equal(encode_json(int_key_map), "
            "'{\\\"values\\\":{\\\"7\\\":9}}')\n"
            "    var decoded_int_key_map = decode_json[HasIntKeyMap]("
            "'{\\\"values\\\":{\\\"-2\\\":3}}')\n"
            "    assert_equal(decoded_int_key_map.values[-2], 3)\n"
            "    var invalid_int_key_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[HasIntKeyMap]("
            "'{\\\"values\\\":{\\\"nope\\\":1}}')\n"
            "    except:\n"
            "        invalid_int_key_rejected = True\n"
            "    assert_true(invalid_int_key_rejected)\n"
            "\n"
            "    var message_map = HasMessageMap()\n"
            "    var mapped_child = Child()\n"
            "    mapped_child.value = 23\n"
            "    message_map.values[String(\"child\")] = mapped_child^\n"
            "    assert_equal(encode_json(message_map), "
            "'{\\\"values\\\":{\\\"child\\\":{\\\"value\\\":23}}}')\n"
            "    var decoded_message_map = decode_json[HasMessageMap]("
            "'{\\\"values\\\":{\\\"child\\\":{\\\"value\\\":29}}}')\n"
            "    assert_equal("
            "decoded_message_map.values[String(\"child\")].value, 29)\n"
            "    var message_map_depth = JsonParseOptions(max_depth=2)\n"
            "    var message_map_depth_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[HasMessageMap]("
            "'{\\\"values\\\":{\\\"child\\\":{}}}', "
            "options=message_map_depth)\n"
            "    except:\n"
            "        message_map_depth_rejected = True\n"
            "    assert_true(message_map_depth_rejected)\n"
            "\n"
            "    var oneof_zero = HasOneof()\n"
            "    oneof_zero.number = 0\n"
            "    oneof_zero.selection_case = 1\n"
            "    assert_equal(encode_json(oneof_zero), "
            "'{\\\"number\\\":0}')\n"
            "    var decoded_oneof = decode_json[HasOneof]("
            "'{\\\"text\\\":\\\"selected\\\"}')\n"
            "    assert_equal(decoded_oneof.selection_case, 2)\n"
            "    assert_equal(decoded_oneof.text, \"selected\")\n"
            "    var null_oneof = decode_json[HasOneof]("
            "'{\\\"number\\\":null}')\n"
            "    assert_equal(null_oneof.selection_case, 0)\n"
            "    var clear_selected_oneof = HasOneof()\n"
            "    clear_selected_oneof.number = 9\n"
            "    clear_selected_oneof.selection_case = 1\n"
            "    var clear_selected_reader = ProtoJsonReader("
            "'{\\\"number\\\":null}')\n"
            "    clear_selected_oneof.merge_json_from("
            "clear_selected_reader)\n"
            "    clear_selected_reader.finish()\n"
            "    assert_equal(clear_selected_oneof.selection_case, 0)\n"
            "    assert_equal(clear_selected_oneof.number, 0)\n"
            "    var preserve_other_oneof = HasOneof()\n"
            "    preserve_other_oneof.text = \"old\"\n"
            "    preserve_other_oneof.selection_case = 2\n"
            "    var preserve_other_reader = ProtoJsonReader("
            "'{\\\"number\\\":null}')\n"
            "    preserve_other_oneof.merge_json_from("
            "preserve_other_reader)\n"
            "    preserve_other_reader.finish()\n"
            "    assert_equal(preserve_other_oneof.selection_case, 2)\n"
            "    assert_equal(preserve_other_oneof.text, \"old\")\n"
            "    var multiple_oneof_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[HasOneof]("
            "'{\\\"number\\\":1,\\\"text\\\":\\\"two\\\"}')\n"
            "    except:\n"
            "        multiple_oneof_rejected = True\n"
            "    assert_true(multiple_oneof_rejected)\n"
            "\n"
            "    var optional_unset = HasOptional()\n"
            "    assert_equal(encode_json(optional_unset), '{}')\n"
            "    assert_equal(encode_json(optional_unset, "
            "options=print_defaults), '{}')\n"
            "    var optional_default = Int32(0)\n"
            "    optional_unset.value = optional_default\n"
            "    assert_equal(encode_json(optional_unset), "
            "'{\\\"value\\\":0}')\n"
            "    var optional_zero = decode_json[HasOptional]("
            "'{\\\"value\\\":0}')\n"
            "    assert_true(optional_zero.value)\n"
            "    assert_equal(optional_zero.value.value(), 0)\n"
            "    var optional_reader = ProtoJsonReader("
            "'{\\\"value\\\":null}')\n"
            "    optional_zero.merge_json_from(optional_reader)\n"
            "    optional_reader.finish()\n"
            "    assert_true(not optional_zero.value)\n"
            "\n"
            "    var empty = Empty()\n"
            "    assert_equal(encode_json(empty), '{}')\n"
            "    var decoded_empty_type = decode_json[Empty]('{}')\n"
            "    assert_equal(encode_json(decoded_empty_type), '{}')\n"
            "    var has_empty = HasEmpty()\n"
            "    has_empty.value = empty^\n"
            "    assert_equal(encode_json(has_empty), "
            "'{\\\"value\\\":{}}')\n"
            "    var decoded_has_empty = decode_json[HasEmpty]("
            "'{\\\"value\\\":{}}')\n"
            "    assert_true(decoded_has_empty.value)\n"
            "\n"
            "    var wrapper = Int32Value()\n"
            "    assert_equal(encode_json(wrapper), '0')\n"
            "    var decoded_wrapper = decode_json[Int32Value]('7')\n"
            "    assert_equal(decoded_wrapper.value, 7)\n"
            "    var null_wrapper_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[Int32Value]('null')\n"
            "    except:\n"
            "        null_wrapper_rejected = True\n"
            "    assert_true(null_wrapper_rejected)\n"
            "    var has_wrapper = HasWrapper()\n"
            "    has_wrapper.value = wrapper^\n"
            "    assert_equal(encode_json(has_wrapper), "
            "'{\\\"value\\\":0}')\n"
            "    var decoded_has_wrapper = decode_json[HasWrapper]("
            "'{\\\"value\\\":7}')\n"
            "    assert_true(decoded_has_wrapper.value)\n"
            "    assert_equal(decoded_has_wrapper.value.value().value, 7)\n"
            "\n"
            "    var timestamp = Timestamp()\n"
            "    assert_equal(encode_json(timestamp), "
            "'\"1970-01-01T00:00:00Z\"')\n"
            "    var decoded_timestamp = decode_json[Timestamp]("
            "'\"1969-12-31T23:59:59.999999999Z\"')\n"
            "    assert_equal(decoded_timestamp.seconds, -1)\n"
            "    assert_equal(decoded_timestamp.nanos, 999999999)\n"
            "    var has_timestamp = HasTimestamp()\n"
            "    has_timestamp.value = timestamp^\n"
            "    assert_equal(encode_json(has_timestamp), "
            "'{\"value\":\"1970-01-01T00:00:00Z\"}')\n"
            "\n"
            "    var duration = Duration()\n"
            "    duration.seconds = -1\n"
            "    duration.nanos = -1000000\n"
            "    assert_equal(encode_json(duration), '\"-1.001s\"')\n"
            "    var decoded_duration = decode_json[Duration]("
            "'\"0.000000001s\"')\n"
            "    assert_equal(decoded_duration.seconds, 0)\n"
            "    assert_equal(decoded_duration.nanos, 1)\n"
            "    var has_duration = HasDuration()\n"
            "    has_duration.value = duration^\n"
            "    assert_equal(encode_json(has_duration), "
            "'{\"value\":\"-1.001s\"}')\n"
            "\n"
            "    var field_mask = FieldMask()\n"
            "    field_mask.paths.append(\"foo_bar\")\n"
            "    assert_equal(encode_json(field_mask), '\"fooBar\"')\n"
            "    var decoded_field_mask = decode_json[FieldMask](\n"
            "'\"fooBar,baz.quxQuux\"')\n"
            "    assert_equal(decoded_field_mask.paths[0], \"foo_bar\")\n"
            "    assert_equal(decoded_field_mask.paths[1], \"baz.qux_quux\")\n"
            "    var has_field_mask = HasFieldMask()\n"
            "    has_field_mask.value = field_mask^\n"
            "    assert_equal(encode_json(has_field_mask),\n"
            "'{\"value\":\"fooBar\"}')\n"
            "\n"
            "    var struct_value = decode_json[Struct](\n"
            "'{\"null\":null,\"list\":[1,true]}')\n"
            "    assert_equal(len(struct_value.fields), 2)\n"
            "    assert_equal(encode_json(struct_value),\n"
            "'{\"null\":null,\"list\":[1.0,true]}')\n"
            "    var dynamic_value = decode_json[Value](\n"
            "'[null,{\"x\":2}]')\n"
            "    assert_equal(dynamic_value.kind_case, 6)\n"
            "    assert_equal(encode_json(dynamic_value),\n"
            "'[null,{\"x\":2.0}]')\n"
            "    var list_value = decode_json[ListValue](\n"
            "'[false,\"text\",{}]')\n"
            "    assert_equal(len(list_value.values), 3)\n"
            "    assert_equal(encode_json(list_value),\n"
            "'[false,\"text\",{}]')\n"
            "    var two_levels = JsonParseOptions(max_depth=2)\n"
            "    _ = decode_json[Value]('[[]]', options=two_levels)\n"
            "    var one_level = JsonParseOptions(max_depth=1)\n"
            "    var value_depth_rejected = False\n"
            "    try:\n"
            "        _ = decode_json[Value]('[[]]', options=one_level)\n"
            "    except:\n"
            "        value_depth_rejected = True\n"
            "    assert_true(value_depth_rejected)\n"
            "    var absent_null = decode_json[HasOptionalNull]('{}')\n"
            "    assert_true(not absent_null.value)\n"
            "    var present_null = decode_json[HasOptionalNull](\n"
            "'{\"value\":null}')\n"
            "    assert_true(present_null.value)\n"
            "    assert_equal(present_null.value.value(), 0)\n"
            "    assert_equal(encode_json(present_null),\n"
            "'{\"value\":null}')\n"
            "    var value_map = decode_json[HasValueMap](\n"
            "'{\"values\":{\"x\":null}}')\n"
            "    assert_equal(value_map.values[String(\"x\")].kind_case, 1)\n"
            "    assert_equal(encode_json(value_map),\n"
            "'{\"values\":{\"x\":null}}')\n"
            "    var value_oneof = decode_json[HasValueOneof](\n"
            "'{\"value\":null}')\n"
            "    assert_equal(value_oneof.selection_case, 1)\n"
            "    assert_true(value_oneof.value)\n"
            "    assert_equal(value_oneof.value.value().kind_case, 1)\n"
            "    assert_equal(encode_json(value_oneof),\n"
            "'{\"value\":null}')\n"
            "    var optional_value = decode_json[HasOptionalValue](\n"
            "'{\"value\":null}')\n"
            "    assert_true(optional_value.value)\n"
            "    assert_equal(optional_value.value.value().kind_case, 1)\n"
            "    assert_equal(encode_json(optional_value),\n"
            "'{\"value\":null}')\n"
            "    var repeated_null = decode_json[HasRepeatedNull](\n"
            "'{\"values\":[\"NULL_VALUE\",0]}')\n"
            "    assert_equal(encode_json(repeated_null),\n"
            "'{\"values\":[null,null]}')\n"
            "    var null_map = decode_json[HasNullMap](\n"
            "'{\"values\":{\"x\":\"NULL_VALUE\"}}')\n"
            "    assert_equal(encode_json(null_map),\n"
            "'{\"values\":{\"x\":null}}')\n"
            "\n"
            "    var tree = decode_json[Tree](\n"
            "'{\"child\":{\"child\":{\"v\":3},\"v\":2},\"v\":1}')\n"
            "    assert_equal(tree.v, 1)\n"
            "    assert_equal(tree.child[0].v, 2)\n"
            "    assert_equal(tree.child[0].child[0].v, 3)\n"
            "    assert_equal(encode_json(tree),\n"
            "'{\"child\":{\"child\":{\"v\":3},\"v\":2},\"v\":1}')\n"
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
