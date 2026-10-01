# Proto3 JSON Timestamp parsing, checked against Python protobuf json_format.

from std.testing import assert_equal, assert_true

from proto import decode_json, encode_json
from vectors_pb import JsonTimestamp


def timestamp_json(value: StringSpan) -> String:
    return String('{"value":"', value, '"}')


def expect_timestamp(value: StringSpan, seconds: Int64, nanos: Int32) raises:
    var decoded = decode_json[JsonTimestamp](timestamp_json(value))
    assert_true(Bool(decoded.value), String(value))
    assert_equal(decoded.value.value().seconds, seconds, String(value))
    assert_equal(decoded.value.value().nanos, nanos, String(value))


def expect_reject(value: StringSpan) raises:
    var raised = False
    try:
        _ = decode_json[JsonTimestamp](timestamp_json(value))
    except:
        raised = True
    assert_true(raised, String("accepted ", value))


def test_canonical_timestamps() raises:
    expect_timestamp("2017-01-15T01:30:15.010Z", 1484443815, 10000000)
    expect_timestamp("2017-12-31T23:59:59.999999999Z", 1514764799, 999999999)
    expect_timestamp("0001-01-01T00:00:00Z", -62135596800, 0)


def test_unpadded_fields_match_python() raises:
    # Weekly JSON fuzz seed 20260827, case 11938.
    var decoded = decode_json[JsonTimestamp](
        '{\n  "value": "2017-01-5T01:30:15.010Z"\n}'
    )
    assert_equal(decoded.value.value().seconds, 1483579815)
    assert_equal(decoded.value.value().nanos, 10000000)
    assert_equal(
        encode_json(decoded), '{"value":"2017-01-05T01:30:15.010Z"}'
    )

    expect_timestamp("2017-1-05T01:30:15Z", 1483579815, 0)
    expect_timestamp("2017-1-5T1:3:5Z", 1483578185, 0)
    expect_timestamp("2016-2-29T0:0:0Z", 1456704000, 0)
    expect_timestamp("2017-01-05T01:30:15+1:0", 1483576215, 0)
    expect_timestamp("2017-1-5T01:30:15.010-05:00", 1483597815, 10000000)


def test_malformed_timestamps() raises:
    expect_reject("017-01-05T01:30:15Z")
    expect_reject("2017-001-05T01:30:15Z")
    expect_reject("2017-01-005T01:30:15Z")
    expect_reject("2017-01-05T001:30:15Z")
    expect_reject("2017-01-05T01:30:015Z")
    expect_reject("2017-01-0T01:30:15Z")
    expect_reject("2017-0-05T01:30:15Z")
    expect_reject("2017-13-05T01:30:15Z")
    expect_reject("2017-2-29T01:30:15Z")
    expect_reject("2017-01-05T24:30:15Z")
    expect_reject("2017-01-05T01:60:15Z")
    expect_reject("2017-01-05T01:30:60Z")
    expect_reject("2017-01-05t01:30:15Z")
    expect_reject("2017-01-05T01:30:15")
    expect_reject("2017-01-05T01:30Z")
    expect_reject("2017-01-05T01:30:15+:00")
    expect_reject("2017-01-05T01:30:15+1:")
    expect_reject("2017-01-05T01:30:15+01")
    expect_reject("2017-01-5T01:30:15.0000000000Z")
    expect_reject("2017-01-5T01:30:15Zx")


def main() raises:
    test_canonical_timestamps()
    test_unpadded_fields_match_python()
    test_malformed_timestamps()
    print("test_json_timestamp: all tests passed")
