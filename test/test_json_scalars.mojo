# Proto3 JSON mapping for generated flat scalar and enum messages.

from std.testing import assert_equal, assert_false, assert_true

from proto import (
    JsonParseOptions,
    JsonPrintOptions,
    decode_json,
    encode_json,
)
from vectors_pb import EchoRequest, EnumValue, Scalars, Status


def expect_reject(text: StringSpan, why: StringSpan) raises:
    var raised = False
    try:
        _ = decode_json[Scalars](text)
    except:
        raised = True
    assert_true(raised, String(why))


def test_print_mapping() raises:
    var message = Scalars()
    message.f_int32 = -7
    message.f_int64 = -9
    message.f_uint32 = 12
    message.f_uint64 = UInt64(18446744073709551615)
    message.f_bool = True
    message.f_float = 1.5
    message.f_double = -2.25
    message.f_string = 'quote " slash \\ newline\n谷歌'
    message.f_bytes = [Byte(0x01), Byte(0x02)]

    var text = encode_json(message)
    assert_true('"fInt32":-7' in text)
    assert_true('"fInt64":"-9"' in text)
    assert_true('"fUint32":12' in text)
    assert_true('"fUint64":"18446744073709551615"' in text)
    assert_true('"fBool":true' in text)
    assert_true('"fBytes":"AQI="' in text)
    assert_true('quote \\" slash \\\\ newline\\n谷歌' in text)

    var decoded = decode_json[Scalars](text)
    assert_equal(decoded.f_int32, -7)
    assert_equal(decoded.f_int64, -9)
    assert_equal(decoded.f_uint64, UInt64(18446744073709551615))
    assert_equal(decoded.f_float, 1.5)
    assert_equal(decoded.f_double, -2.25)
    assert_equal(decoded.f_string, message.f_string)
    assert_equal(len(decoded.f_bytes), 2)
    assert_equal(decoded.f_bytes[1], 2)


def test_options_and_defaults() raises:
    assert_equal(encode_json(Scalars()), "{}")

    var print_options = JsonPrintOptions(
        preserve_proto_field_names=True,
        always_print_fields_with_no_presence=True,
    )
    var text = encode_json(Scalars(), options=print_options)
    assert_true('"f_int32":0' in text)
    assert_true('"f_int64":"0"' in text)
    assert_true('"f_bool":false' in text)
    assert_true('"f_string":""' in text)

    var by_proto_name = decode_json[Scalars]('{"f_int32":7}')
    assert_equal(by_proto_name.f_int32, 7)
    var null_value = decode_json[Scalars]('{"fInt32":null}')
    assert_equal(null_value.f_int32, 0)


def test_integer_forms() raises:
    var message = decode_json[Scalars](
        '{"fInt32":100000.000,"fSint32":"1e5",'
        '"fInt64":"-9223372036854775808",'
        '"fUint64":"18446744073709551615"}'
    )
    assert_equal(message.f_int32, 100000)
    assert_equal(message.f_sint32, 100000)
    assert_equal(message.f_int64, Int64(from_bits=UInt64(0x8000000000000000)))
    assert_equal(message.f_uint64, UInt64(0xFFFFFFFFFFFFFFFF))

    expect_reject('{"fInt32":2147483648}', "int32 overflow")
    expect_reject('{"fUint32":-1}', "negative uint32")
    expect_reject('{"fInt32":0.5}', "fractional integer")
    expect_reject('{"fInt32":" 1"}', "quoted integer whitespace")
    expect_reject('{"fInt32":01}', "leading zero")
    expect_reject('{"fInt32":+1}', "leading plus")


def test_float_specials() raises:
    var message = decode_json[Scalars](
        '{"fFloat":"Infinity","fDouble":"-Infinity"}'
    )
    assert_equal(UInt32(message.f_float.to_bits()), UInt32(0x7F800000))
    assert_equal(UInt64(message.f_double.to_bits()), UInt64(0xFFF0000000000000))
    var text = encode_json(message)
    assert_true('"fFloat":"Infinity"' in text)
    assert_true('"fDouble":"-Infinity"' in text)

    expect_reject('{"fFloat":NaN}', "unquoted NaN")
    expect_reject('{"fFloat":3.5e38}', "float overflow")
    expect_reject('{"fDouble":1.9e308}', "double overflow")

    var zero = decode_json[Scalars]('{"fInt32":0e99999}')
    assert_equal(zero.f_int32, 0)


def test_strings_and_bytes() raises:
    var message = decode_json[Scalars](
        '{"fString":"\\u8c37\\u6b4c \\uD83D\\uDE01 \\u0000","fBytes":"-_"}'
    )
    assert_equal(message.f_string, "谷歌 😁 \0")
    assert_equal(len(message.f_bytes), 1)
    assert_equal(message.f_bytes[0], 0xFB)

    expect_reject('{"fString":"\\uD800"}', "unpaired high surrogate")
    expect_reject('{"fString":"\\uDC00"}', "unpaired low surrogate")
    expect_reject('{"fString":1}', "string type")
    expect_reject('{"fBytes":"A"}', "base64 length")
    expect_reject('{"fBytes":"A!"}', "base64 alphabet")


def test_structure_and_unknown_fields() raises:
    expect_reject('{"fInt32":1,"fInt32":2}', "duplicate JSON name")
    expect_reject('{"fInt32":1,"f_int32":2}', "duplicate field-name aliases")
    expect_reject('{"unknown":1}', "unknown field")
    expect_reject('{"fInt32":1,}', "trailing comma")
    expect_reject('{"fInt32":1} false', "trailing content")
    expect_reject("null", "top-level null")

    var options = JsonParseOptions(ignore_unknown_fields=True)
    var accepted = decode_json[Scalars](
        '{"unknown":{"nested":[1,true,null]},"fInt32":3}',
        options=options,
    )
    assert_equal(accepted.f_int32, 3)

    var shallow = JsonParseOptions(ignore_unknown_fields=True, max_depth=1)
    var raised = False
    try:
        _ = decode_json[Scalars]('{"unknown":{}}', options=shallow)
    except:
        raised = True
    assert_true(raised, "unknown values obey the nesting limit")


def test_simple_generated_message() raises:
    var request = decode_json[EchoRequest]('{"message":"hello"}')
    assert_equal(request.message, "hello")
    assert_equal(encode_json(request), '{"message":"hello"}')


def test_singular_enum_mapping() raises:
    var active = EnumValue()
    active.status = Status.STATUS_ACTIVE
    assert_equal(encode_json(active), '{"status":"STATUS_ACTIVE"}')

    var aliased = decode_json[EnumValue]('{"status":"STATUS_ENABLED"}')
    assert_equal(aliased.status, Status.STATUS_ACTIVE)
    assert_equal(encode_json(aliased), '{"status":"STATUS_ACTIVE"}')

    var unknown = decode_json[EnumValue]('{"status":123}')
    assert_equal(unknown.status, 123)
    assert_equal(encode_json(unknown), '{"status":123}')

    var negative = decode_json[EnumValue]('{"status":"STATUS_NEGATIVE"}')
    assert_equal(negative.status, -1)

    var null_value = decode_json[EnumValue]('{"status":null}')
    assert_equal(null_value.status, Status.STATUS_UNSPECIFIED)

    var print_defaults = JsonPrintOptions(
        always_print_fields_with_no_presence=True
    )
    assert_equal(
        encode_json(EnumValue(), options=print_defaults),
        '{"status":"STATUS_UNSPECIFIED"}',
    )

    var raised = False
    try:
        _ = decode_json[EnumValue]('{"status":"STATUS_MISSING"}')
    except:
        raised = True
    assert_true(raised, "unknown enum name")

    raised = False
    try:
        _ = decode_json[EnumValue]('{"status":"1"}')
    except:
        raised = True
    assert_true(raised, "quoted enum integer")

    var ignore_unknown = JsonParseOptions(ignore_unknown_fields=True)
    var ignored = decode_json[EnumValue](
        '{"status":"STATUS_MISSING"}', options=ignore_unknown
    )
    assert_equal(ignored.status, Status.STATUS_UNSPECIFIED)


def main() raises:
    test_print_mapping()
    test_options_and_defaults()
    test_integer_forms()
    test_float_specials()
    test_strings_and_bytes()
    test_structure_and_unknown_fields()
    test_simple_generated_message()
    test_singular_enum_mapping()
    print("test_json_scalars: all tests passed")
