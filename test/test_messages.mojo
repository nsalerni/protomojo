# Message-level tests against golden bytes from the reference Python
# protobuf implementation (test/proto_golden.mojo, generated).

from std.testing import assert_equal, assert_true

from testutil import from_hex, to_hex
from proto import decode, encode
from proto_golden import (
    ECHO_PING,
    NESTED_ENC,
    NESTED_FULL,
    NESTED_ONEOF_NUM,
    SCALARS_EMPTY,
    SCALARS_FULL,
    SCALARS_NEG_INT32,
)
from proto_messages import EchoRequest, Nested, Scalars


def full_scalars() -> Scalars:
    var s = Scalars()
    s.f_int32 = 150
    s.f_int64 = -2
    s.f_uint32 = 300
    s.f_uint64 = UInt64(1) << 60
    s.f_sint32 = -1
    s.f_sint64 = -(Int64(1) << 40)
    s.f_bool = True
    s.f_fixed32 = 0xDEADBEEF
    s.f_fixed64 = 0x0123456789ABCDEF
    s.f_sfixed32 = -2
    s.f_sfixed64 = -3
    s.f_float = 1.5
    s.f_double = -2.25
    s.f_string = "héllo"
    s.f_bytes = [Byte(0x00), Byte(0x01), Byte(0xFF)]
    s.f_big_field = 7
    return s^


def test_scalars_encode_matches_python() raises:
    assert_equal(to_hex(encode(full_scalars())), String(SCALARS_FULL))
    assert_equal(to_hex(encode(Scalars())), String(SCALARS_EMPTY))
    var neg = Scalars()
    neg.f_int32 = -1
    assert_equal(to_hex(encode(neg)), String(SCALARS_NEG_INT32))


def test_scalars_decode_golden() raises:
    var s = decode[Scalars](Span(from_hex(SCALARS_FULL)))
    assert_equal(s.f_int32, 150)
    assert_equal(s.f_int64, -2)
    assert_equal(s.f_uint32, 300)
    assert_equal(s.f_uint64, UInt64(1) << 60)
    assert_equal(s.f_sint32, -1)
    assert_equal(s.f_sint64, -(Int64(1) << 40))
    assert_equal(s.f_bool, True)
    assert_equal(s.f_fixed32, UInt32(0xDEADBEEF))
    assert_equal(s.f_fixed64, UInt64(0x0123456789ABCDEF))
    assert_equal(s.f_sfixed32, -2)
    assert_equal(s.f_sfixed64, -3)
    assert_equal(s.f_float, Float32(1.5))
    assert_equal(s.f_double, Float64(-2.25))
    assert_equal(s.f_string, "héllo")
    assert_equal(len(s.f_bytes), 3)
    assert_equal(s.f_bytes[2], 0xFF)
    assert_equal(s.f_big_field, 7)

    var neg = decode[Scalars](Span(from_hex(SCALARS_NEG_INT32)))
    assert_equal(neg.f_int32, -1)


def test_scalars_roundtrip() raises:
    var bytes = encode(full_scalars())
    var s = decode[Scalars](Span(bytes))
    assert_equal(to_hex(encode(s)), to_hex(bytes))


def test_nested_encode_matches_python() raises:
    var n = Nested()
    var inner = Scalars()
    inner.f_int32 = 1
    inner.f_string = "x"
    n.inner = inner^
    n.packed_ints = [Int32(1), Int32(2), Int32(300), Int32(-1)]
    n.names = ["a", "bb", ""]
    var i1 = Scalars()
    i1.f_bool = True
    n.inners.append(i1^)
    n.inners.append(Scalars())
    n.counts["one"] = 1
    n.choice_case = 6
    n.as_text = "chosen"
    assert_equal(to_hex(encode(n)), String(NESTED_ENC))


def test_nested_decode_golden() raises:
    var n = decode[Nested](Span(from_hex(NESTED_FULL)))
    assert_true(Bool(n.inner), "inner must be present")
    assert_equal(n.inner.value().f_int32, 1)
    assert_equal(n.inner.value().f_string, "x")
    assert_equal(len(n.packed_ints), 4)
    assert_equal(n.packed_ints[2], 300)
    assert_equal(n.packed_ints[3], -1)
    assert_equal(len(n.names), 3)
    assert_equal(n.names[1], "bb")
    assert_equal(n.names[2], "")
    assert_equal(len(n.inners), 2)
    assert_equal(n.inners[0].f_bool, True)
    assert_equal(n.inners[1].f_bool, False)
    assert_equal(len(n.counts), 2)
    assert_equal(n.counts["one"], 1)
    assert_equal(n.counts["two"], 2)
    assert_equal(n.choice_case, 6)
    assert_equal(n.as_text, "chosen")

    var n2 = decode[Nested](Span(from_hex(NESTED_ONEOF_NUM)))
    assert_equal(n2.choice_case, 7)
    assert_equal(n2.as_num, -5)


def test_unknown_fields_skipped() raises:
    # Scalars bytes parsed as EchoRequest: only field 1 shared; the rest
    # must be skipped without error (here field 1 has a different type,
    # so use Nested bytes where field 1 is length-delimited like string).
    var e = decode[EchoRequest](Span(from_hex(NESTED_FULL)))
    # field 1 (inner submessage) is LEN like string, decoded as garbage
    # string — but fields 2..7 must be skipped cleanly.
    _ = e^


def test_echo() raises:
    var e = EchoRequest(message="ping")
    assert_equal(to_hex(encode(e)), String(ECHO_PING))
    var d = decode[EchoRequest](Span(from_hex(ECHO_PING)))
    assert_equal(d.message, "ping")


def main() raises:
    test_scalars_encode_matches_python()
    test_scalars_decode_golden()
    test_scalars_roundtrip()
    test_nested_encode_matches_python()
    test_nested_decode_golden()
    test_unknown_fields_skipped()
    test_echo()
    print("test_messages: all tests passed")
