# Wire-format primitive tests: varint, zigzag, fixed, tags, skip.

from std.testing import assert_equal, assert_true

from testutil import from_hex, to_hex
from proto import (
    WIRE_LEN,
    WIRE_VARINT,
    WireReader,
    WireWriter,
    zigzag_decode32,
    zigzag_decode64,
    zigzag_encode32,
    zigzag_encode64,
)


def check_varint(v: UInt64, expected_hex: StringSpan) raises:
    var w = WireWriter()
    w.varint(v)
    var got = w^.take()
    assert_equal(to_hex(got), String(expected_hex))
    var r = WireReader(got)
    assert_equal(r.varint(), v)
    assert_true(r.done())


def test_varint() raises:
    # Examples from protobuf.dev/programming-guides/encoding
    check_varint(0, "00")
    check_varint(1, "01")
    check_varint(127, "7f")
    check_varint(128, "8001")
    check_varint(150, "9601")
    check_varint(300, "ac02")
    check_varint(UInt64.MAX, "ffffffffffffffffff01")


def test_varint_errors() raises:
    # Truncated
    var r = WireReader(from_hex("80"))
    var raised = False
    try:
        _ = r.varint()
    except:
        raised = True
    assert_true(raised, "truncated varint must raise")

    # 11-byte varint (too long)
    var r2 = WireReader(from_hex("ffffffffffffffffffff01"))
    raised = False
    try:
        _ = r2.varint()
    except:
        raised = True
    assert_true(raised, "overlong varint must raise")


def test_zigzag() raises:
    # Table from the encoding guide.
    assert_equal(zigzag_encode32(0), 0)
    assert_equal(zigzag_encode32(-1), 1)
    assert_equal(zigzag_encode32(1), 2)
    assert_equal(zigzag_encode32(-2), 3)
    assert_equal(zigzag_encode32(2147483647), 4294967294)
    assert_equal(zigzag_encode32(-2147483648), 4294967295)
    assert_equal(zigzag_encode64(Int64.MAX), UInt64.MAX - 1)
    assert_equal(zigzag_encode64(Int64.MIN), UInt64.MAX)
    for v in [0, -1, 1, -2, 2, 2147483647, -2147483648]:
        assert_equal(Int(zigzag_decode32(zigzag_encode32(Int32(v)))), v)
        assert_equal(Int(zigzag_decode64(zigzag_encode64(Int64(v)))), v)


def test_sint32_high_bit_regression() raises:
    # Regression: Mojo 1.0 folded UInt64(zigzag_encode32(v)) into a
    # sign-extending cast, emitting a 10-byte varint where the reference
    # implementation emits 5 bytes. Golden bytes from Python protobuf.
    var w = WireWriter()
    w.sint32(5, -1305184409)
    assert_equal(to_hex(w^.take()), "28b1a2dcdc09")
    var w2 = WireWriter()
    w2.uint32(3, 0xDEADBEEF)
    assert_equal(to_hex(w2^.take()), "18effdb6f50d")


def test_fixed_and_floats() raises:
    var w = WireWriter()
    w.fixed32(0xDEADBEEF)
    w.fixed64(0x0123456789ABCDEF)
    var buf = w^.take()
    assert_equal(to_hex(buf), "efbeaddeefcdab8967452301")
    var r = WireReader(buf)
    assert_equal(r.fixed32(), 0xDEADBEEF)
    assert_equal(r.fixed64(), 0x0123456789ABCDEF)

    var w2 = WireWriter()
    w2.float_field(12, 1.5)
    w2.double_field(13, -2.25)
    var buf2 = w2^.take()
    # From the Python-generated SCALARS_FULL golden.
    assert_equal(to_hex(buf2), "650000c03f6900000000000002c0")
    var r2 = WireReader(buf2)
    var t = r2.read_tag()
    assert_equal(t[0], 12)
    assert_equal(r2.float_value(), Float32(1.5))
    t = r2.read_tag()
    assert_equal(t[0], 13)
    assert_equal(r2.double_value(), Float64(-2.25))


def test_tags_and_skip() raises:
    var w = WireWriter()
    w.int32(1, 150)
    w.string_field(14, "hi")
    w.tag(1000, WIRE_VARINT)
    w.varint(7)
    var buf = w^.take()

    var r = WireReader(buf)
    # Skip everything without knowing the schema.
    var fields = List[Int]()
    while not r.done():
        var tag = r.read_tag()
        fields.append(tag[0])
        r.skip(tag[1])
    assert_equal(len(fields), 3)
    assert_equal(fields[0], 1)
    assert_equal(fields[1], 14)
    assert_equal(fields[2], 1000)


def test_field_zero_rejected() raises:
    var r = WireReader(from_hex("00"))
    var raised = False
    try:
        _ = r.read_tag()
    except:
        raised = True
    assert_true(raised, "field number 0 must raise")


def main() raises:
    test_varint()
    test_varint_errors()
    test_zigzag()
    test_sint32_high_bit_regression()
    test_fixed_and_floats()
    test_tags_and_skip()
    test_field_zero_rejected()
    print("test_wire: all tests passed")
