# Proto3 JSON parsing of non-string map keys.

from std.testing import assert_equal, assert_true

from proto import decode_json
from vectors_pb import JsonKeyMaps


def expect_reject(text: StringSpan, why: StringSpan) raises:
    var raised = False
    try:
        _ = decode_json[JsonKeyMaps](text)
    except:
        raised = True
    assert_true(raised, String(why))


def test_integer_keys_follow_quoted_integer_rules() raises:
    var parsed = decode_json[JsonKeyMaps](
        '{"int32Values":{"-2":"a","+3":"b","1e2":"c","4.0":"d"},'
        '"int64Values":{"-9223372036854775808":"e"},'
        '"uint64Values":{"18446744073709551615":"f"},'
        '"sint32Values":{"-0":"g"},'
        '"fixed32Values":{"4294967295":"h"}}'
    )
    assert_equal(parsed.int32_values[-2], "a")
    assert_equal(parsed.int32_values[3], "b")
    assert_equal(parsed.int32_values[100], "c")
    assert_equal(parsed.int32_values[4], "d")
    assert_equal(parsed.int64_values[Int64.MIN], "e")
    assert_equal(parsed.uint64_values[UInt64.MAX], "f")
    assert_equal(parsed.sint32_values[0], "g")
    assert_equal(parsed.fixed32_values[UInt32.MAX], "h")


def test_integer_keys_reject_padding_and_nested_quotes() raises:
    expect_reject('{"int32Values":{" 1":"a"}}', "leading space")
    expect_reject('{"int32Values":{"1 ":"a"}}', "trailing space")
    expect_reject('{"int32Values":{"\\"1\\"":"a"}}', "quoted int32 key")
    expect_reject('{"int64Values":{"\\"5\\"":"a"}}', "quoted int64 key")
    expect_reject('{"uint64Values":{" 5":"a"}}', "padded uint64 key")
    expect_reject('{"sfixed64Values":{"\\" 5\\"":"a"}}', "quoted padded key")
    expect_reject('{"int32Values":{"":"a"}}', "empty key")
    expect_reject('{"int32Values":{"2147483648":"a"}}', "int32 overflow")
    # Python's int() also takes these, but quoted integer values reject
    # them, so keys do too.
    expect_reject('{"int32Values":{"\\t1":"a"}}', "leading tab")
    expect_reject('{"int32Values":{"1\\n":"a"}}', "trailing newline")
    expect_reject('{"int32Values":{"01":"a"}}', "leading zero")


def test_bool_keys_are_exact() raises:
    var parsed = decode_json[JsonKeyMaps](
        '{"boolValues":{"true":"t","false":"f"}}'
    )
    assert_equal(parsed.bool_values[True], "t")
    assert_equal(parsed.bool_values[False], "f")
    expect_reject('{"boolValues":{" true":"a"}}', "leading space")
    expect_reject('{"boolValues":{"false ":"a"}}', "trailing space")
    expect_reject('{"boolValues":{"True":"a"}}', "capitalized")
    expect_reject('{"boolValues":{"1":"a"}}', "numeric bool key")


def main() raises:
    test_integer_keys_follow_quoted_integer_rules()
    test_integer_keys_reject_padding_and_nested_quotes()
    test_bool_keys_are_exact()
