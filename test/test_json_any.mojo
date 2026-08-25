# Proto3 JSON mapping for google.protobuf.Any and generated type resolvers.

from std.testing import assert_equal, assert_false, assert_true

from any_pb import Any
from proto import (
    JsonParseOptions,
    JsonPrintOptions,
    decode,
    decode_json,
    encode,
    encode_json,
)
from vectors_pb import JsonAnyParent, JsonAnyPayload, Scalars
from vectors_pb_json_resolver import json_type_resolver
from wrappers_pb import Int32Value


def parse_options(
    *, ignore_unknown_fields: Bool = False, max_depth: Int = 100
) -> JsonParseOptions:
    return JsonParseOptions(
        ignore_unknown_fields=ignore_unknown_fields,
        max_depth=max_depth,
        type_resolver=json_type_resolver(),
    )


def print_options(
    *,
    preserve_proto_field_names: Bool = False,
    always_print_fields_with_no_presence: Bool = False,
) -> JsonPrintOptions:
    return JsonPrintOptions(
        preserve_proto_field_names=preserve_proto_field_names,
        always_print_fields_with_no_presence=(
            always_print_fields_with_no_presence
        ),
        type_resolver=json_type_resolver(),
    )


def expect_parse_reject(text: StringSpan, why: StringSpan) raises:
    var raised = False
    try:
        _ = decode_json[Any](text, options=parse_options())
    except:
        raised = True
    assert_true(raised, String(why))


def test_empty_any() raises:
    var empty = Any()
    assert_equal(encode_json(empty), "{}")
    var parsed = decode_json[Any]("{}")
    assert_equal(parsed.type_url, "")
    assert_equal(len(parsed.value), 0)


def test_ordinary_message() raises:
    var payload = JsonAnyPayload()
    payload.id = 17
    payload.note = "resolved"

    var value = Any()
    value.type_url = (
        "type.googleapis.com/grpcmojo.test.JsonAnyPayload"
    )
    value.value = encode(payload)
    var text = encode_json(value, options=print_options())
    assert_equal(
        text,
        '{"@type":"type.googleapis.com/grpcmojo.test.JsonAnyPayload",'
        '"id":17,"note":"resolved"}',
    )

    var parsed = decode_json[Any](
        '{"id":17,"note":"resolved",'
        '"@type":"type.googleapis.com/grpcmojo.test.JsonAnyPayload"}',
        options=parse_options(),
    )
    assert_equal(parsed.type_url, value.type_url)
    var decoded = decode[JsonAnyPayload](Span(parsed.value))
    assert_equal(decoded.id, 17)
    assert_equal(decoded.note, "resolved")

    var prefixed = decode_json[Any](
        '{"@type":"https://schemas.example/types/'
        'grpcmojo.test.JsonAnyPayload","id":8}',
        options=parse_options(),
    )
    assert_equal(
        prefixed.type_url,
        "https://schemas.example/types/grpcmojo.test.JsonAnyPayload",
    )
    assert_equal(decode[JsonAnyPayload](Span(prefixed.value)).id, 8)


def test_well_known_value_form() raises:
    var wrapped = Int32Value()
    wrapped.value = 123
    var value = Any()
    value.type_url = "type.googleapis.com/google.protobuf.Int32Value"
    value.value = encode(wrapped)
    assert_equal(
        encode_json(value, options=print_options()),
        '{"@type":"type.googleapis.com/google.protobuf.Int32Value",'
        '"value":123}',
    )

    var parsed = decode_json[Any](
        '{"value":123,'
        '"@type":"type.googleapis.com/google.protobuf.Int32Value"}',
        options=parse_options(),
    )
    assert_equal(decode[Int32Value](Span(parsed.value)).value, 123)


def test_nested_any() raises:
    var payload = JsonAnyPayload()
    payload.id = 5
    var inner = Any()
    inner.type_url = "type.googleapis.com/grpcmojo.test.JsonAnyPayload"
    inner.value = encode(payload)

    var outer = Any()
    outer.type_url = "type.googleapis.com/google.protobuf.Any"
    outer.value = encode(inner)
    var text = encode_json(outer, options=print_options())
    assert_equal(
        text,
        '{"@type":"type.googleapis.com/google.protobuf.Any","value":'
        '{"@type":"type.googleapis.com/grpcmojo.test.JsonAnyPayload",'
        '"id":5}}',
    )

    var parsed = decode_json[Any](text, options=parse_options())
    var parsed_inner = decode[Any](Span(parsed.value))
    assert_equal(parsed_inner.type_url, inner.type_url)
    assert_equal(
        decode[JsonAnyPayload](Span(parsed_inner.value)).id,
        5,
    )


def test_any_in_generated_fields() raises:
    var text = (
        '{"value":null,"values":['
        '{"@type":"type.googleapis.com/grpcmojo.test.JsonAnyPayload",'
        '"id":1}],"mapped":{"primary":'
        '{"@type":"type.googleapis.com/grpcmojo.test.JsonAnyPayload",'
        '"id":2}},"selected":'
        '{"@type":"type.googleapis.com/grpcmojo.test.JsonAnyPayload",'
        '"id":3}}'
    )
    var parent = decode_json[JsonAnyParent](text, options=parse_options())
    assert_false(Bool(parent.value))
    assert_equal(len(parent.values), 1)
    assert_equal(
        decode[JsonAnyPayload](Span(parent.values[0].value)).id,
        1,
    )
    assert_equal(
        decode[JsonAnyPayload](Span(parent.mapped["primary"].value)).id,
        2,
    )
    assert_equal(parent.selection_case, 4)
    assert_true(Bool(parent.selected))
    assert_equal(
        decode[JsonAnyPayload](Span(parent.selected.value().value)).id,
        3,
    )


def test_options_propagate() raises:
    var payload = Scalars()
    payload.f_int32 = 9
    var value = Any()
    value.type_url = "type.googleapis.com/grpcmojo.test.Scalars"
    value.value = encode(payload)
    var text = encode_json(
        value,
        options=print_options(preserve_proto_field_names=True),
    )
    assert_true('"f_int32":9' in text)

    var defaults = JsonAnyPayload()
    value.type_url = (
        "type.googleapis.com/grpcmojo.test.JsonAnyPayload"
    )
    value.value = encode(defaults)
    text = encode_json(
        value,
        options=print_options(
            always_print_fields_with_no_presence=True
        ),
    )
    assert_true('"id":0' in text)
    assert_true('"note":""' in text)

    var ignored = decode_json[Any](
        '{"@type":"type.googleapis.com/grpcmojo.test.JsonAnyPayload",'
        '"unknown":7,"id":4}',
        options=parse_options(ignore_unknown_fields=True),
    )
    assert_equal(decode[JsonAnyPayload](Span(ignored.value)).id, 4)


def test_depth_boundaries() raises:
    var nested = (
        '{"@type":"type.googleapis.com/google.protobuf.Any","value":'
        '{"@type":"type.googleapis.com/grpcmojo.test.JsonAnyPayload",'
        '"id":1}}'
    )
    _ = decode_json[Any](nested, options=parse_options(max_depth=2))
    var raised = False
    try:
        _ = decode_json[Any](nested, options=parse_options(max_depth=1))
    except:
        raised = True
    assert_true(raised, "nested Any rejects one level below its depth")

    var repeated = (
        '{"values":[{"@type":"type.googleapis.com/'
        'grpcmojo.test.JsonAnyPayload","id":1}]}'
    )
    _ = decode_json[JsonAnyParent](
        repeated, options=parse_options(max_depth=3)
    )
    raised = False
    try:
        _ = decode_json[JsonAnyParent](
            repeated, options=parse_options(max_depth=2)
        )
    except:
        raised = True
    assert_true(raised, "Any array elements obey the exact depth limit")

    var structured = (
        '{"@type":"type.googleapis.com/google.protobuf.Struct",'
        '"value":{"nested":{"x":1}}}'
    )
    _ = decode_json[Any](structured, options=parse_options(max_depth=3))
    raised = False
    try:
        _ = decode_json[Any](
            structured, options=parse_options(max_depth=2)
        )
    except:
        raised = True
    assert_true(raised, "Struct inside Any shares the remaining depth budget")


def test_rejections() raises:
    expect_parse_reject('{"id":1}', "missing @type")
    expect_parse_reject('{"@type":1}', "non-string @type")
    expect_parse_reject('{"@type":""}', "empty type URL")
    expect_parse_reject(
        '{"@type":"grpcmojo.test.JsonAnyPayload","id":1}',
        "type URL without a prefix",
    )
    expect_parse_reject(
        '{"@type":"type.googleapis.com/grpcmojo.test.Missing"}',
        "unresolved type URL",
    )
    expect_parse_reject(
        '{"@type":"type.googleapis.com/grpcmojo.test.JsonAnyPayload",'
        '"@type":"type.googleapis.com/grpcmojo.test.JsonAnyPayload"}',
        "duplicate @type",
    )
    expect_parse_reject(
        '{"@type":"type.googleapis.com/google.protobuf.Int32Value"}',
        "missing well-known value",
    )
    expect_parse_reject(
        '{"@type":"type.googleapis.com/google.protobuf.Int32Value",'
        '"value":1,"extra":2}',
        "extra well-known field",
    )
    expect_parse_reject(
        '{"@type":"type.googleapis.com/google.protobuf.Int32Value",'
        '"value":1,"value":2}',
        "duplicate well-known value",
    )
    expect_parse_reject(
        '{"@type":"type.googleapis.com/grpcmojo.test.JsonAnyPayload",'
        '"unknown":1}',
        "unknown embedded field",
    )

    var unresolved = Any()
    unresolved.type_url = (
        "type.googleapis.com/grpcmojo.test.JsonAnyPayload"
    )
    var raised = False
    try:
        _ = encode_json(unresolved)
    except:
        raised = True
    assert_true(raised, "non-empty Any requires a print resolver")

    raised = False
    try:
        _ = decode_json[Any](
            '{"@type":"type.googleapis.com/'
            'grpcmojo.test.JsonAnyPayload","id":1}'
        )
    except:
        raised = True
    assert_true(raised, "non-empty Any requires a parse resolver")

    unresolved.type_url = "type.googleapis.com/grpcmojo.test.Missing"
    raised = False
    try:
        _ = encode_json(unresolved, options=print_options())
    except:
        raised = True
    assert_true(raised, "configured resolver rejects an unknown type")

    unresolved.type_url = "grpcmojo.test.JsonAnyPayload"
    raised = False
    try:
        _ = encode_json(unresolved, options=print_options())
    except:
        raised = True
    assert_true(raised, "print rejects a type name without a URL prefix")

    unresolved.type_url = ""
    unresolved.value = [Byte(0x08), Byte(0x01)]
    raised = False
    try:
        _ = encode_json(unresolved, options=print_options())
    except:
        raised = True
    assert_true(raised, "print rejects bytes without a type URL")

    unresolved.type_url = (
        "type.googleapis.com/grpcmojo.test.JsonAnyPayload"
    )
    unresolved.value = [Byte(0x0F)]
    raised = False
    try:
        _ = encode_json(unresolved, options=print_options())
    except:
        raised = True
    assert_true(raised, "malformed embedded wire value")


def main() raises:
    test_empty_any()
    test_ordinary_message()
    test_well_known_value_form()
    test_nested_any()
    test_any_in_generated_fields()
    test_options_propagate()
    test_depth_boundaries()
    test_rejections()
    print("test_json_any: all tests passed")
