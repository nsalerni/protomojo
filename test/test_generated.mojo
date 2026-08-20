# The protoc-gen-mojo output must pass the same golden-vector tests as
# the hand-written reference messages.

from std.testing import assert_equal, assert_true

from testutil import from_hex, to_hex
from proto import decode, encode
from proto_golden import (
    NESTED_ENC,
    NESTED_FULL,
    NESTED_ONEOF_NUM,
    SCALARS_EMPTY,
    SCALARS_FULL,
    SCALARS_NEG_INT32,
)
from vectors_pb import Nested, Scalars


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


def test_generated_scalars() raises:
    assert_equal(to_hex(encode(full_scalars())), String(SCALARS_FULL))
    assert_equal(to_hex(encode(Scalars())), String(SCALARS_EMPTY))
    var neg = Scalars()
    neg.f_int32 = -1
    assert_equal(to_hex(encode(neg)), String(SCALARS_NEG_INT32))

    var s = decode[Scalars](Span(from_hex(SCALARS_FULL)))
    assert_equal(s.f_int32, 150)
    assert_equal(s.f_sint64, -(Int64(1) << 40))
    assert_equal(s.f_string, "héllo")
    assert_equal(s.f_big_field, 7)
    # Full roundtrip byte equality.
    assert_equal(to_hex(encode(s)), String(SCALARS_FULL))


def test_generated_nested() raises:
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

    var d = decode[Nested](Span(from_hex(NESTED_FULL)))
    assert_true(Bool(d.inner), "inner present")
    assert_equal(d.inner.value().f_string, "x")
    assert_equal(len(d.packed_ints), 4)
    assert_equal(d.packed_ints[3], -1)
    assert_equal(d.counts["two"], 2)
    assert_equal(d.choice_case, 6)
    assert_equal(d.as_text, "chosen")

    var d2 = decode[Nested](Span(from_hex(NESTED_ONEOF_NUM)))
    assert_equal(d2.choice_case, 7)
    assert_equal(d2.as_num, -5)


def main() raises:
    test_generated_scalars()
    test_generated_nested()
    print("test_generated: all tests passed")
