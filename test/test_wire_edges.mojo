# Wire-codec edge cases: error paths, extreme values, merge semantics.

from std.testing import assert_equal, assert_false, assert_true

from testutil import from_hex, to_hex
from proto import (
    MAX_DECODE_DEPTH,
    WIRE_FIXED32,
    WIRE_FIXED64,
    WIRE_LEN,
    WIRE_VARINT,
    WireReader,
    WireWriter,
    decode,
    encode,
    zigzag_decode32,
    zigzag_decode64,
)
from proto_messages import Nested, Scalars
from vectors_pb import Nested as GenNested


def test_fixed_truncation() raises:
    # fixed32 with only 3 bytes left.
    var r = WireReader(from_hex("aabbcc"))
    var raised = False
    var msg = String()
    try:
        _ = r.fixed32()
    except e:
        raised = True
        msg = String(e)
    assert_true(raised, "short fixed32 must raise")
    assert_true("truncated fixed32" in msg)

    # fixed64 with exactly 7 bytes left: the second 4-byte half is short.
    # (The error surfaces from the inner fixed32 read.)
    var r2 = WireReader(from_hex("00112233445566"))
    raised = False
    msg = String()
    try:
        _ = r2.fixed64()
    except e:
        raised = True
        msg = String(e)
    assert_true(raised, "7-byte fixed64 must raise")
    assert_true("truncated fixed32" in msg)


def test_bytes_value_overrun() raises:
    # Declared length 5 with only 2 value bytes present.
    var r = WireReader(from_hex("05abcd"))
    var raised = False
    var msg = String()
    try:
        _ = r.bytes_value()
    except e:
        raised = True
        msg = String(e)
    assert_true(raised, "overrun length must raise")
    assert_true("truncated length-delimited" in msg)

    # Length varint of UInt64.MAX: Int(varint) wraps negative, so the
    # n < 0 guard fires.
    var r2 = WireReader(from_hex("ffffffffffffffffff01"))
    raised = False
    msg = String()
    try:
        _ = r2.bytes_value()
    except e:
        raised = True
        msg = String(e)
    assert_true(raised, "negative-wrapped length must raise")
    assert_true("truncated length-delimited" in msg)

    # Hostile 63-bit length (2^63 - 1): must raise, not overflow the
    # bounds check into a slice crash (regression: the check previously
    # computed `pos + n`, which wrapped negative).
    var r3 = WireReader(from_hex("ffffffffffffffff7f"))
    raised = False
    msg = String()
    try:
        _ = r3.bytes_value()
    except e:
        raised = True
        msg = String(e)
    assert_true(raised, "63-bit length must raise, not crash")
    assert_true("truncated length-delimited" in msg)


def test_skip_unsupported_wire_types() raises:
    for wt in [3, 4, 6, 7]:
        var r = WireReader(from_hex("00"))
        var raised = False
        var msg = String()
        try:
            r.skip(wt)
        except e:
            raised = True
            msg = String(e)
        assert_true(raised, "wire type " + String(wt) + " must raise")
        assert_true("unsupported wire type" in msg)


def test_skip_fixed_advances() raises:
    var w = WireWriter()
    w.fixed32(0xAABBCCDD)
    w.fixed64(0x1122334455667788)
    w.varint(7)
    var buf = w^.take()

    var r = WireReader(buf)
    r.skip(WIRE_FIXED32)
    assert_equal(r.pos, 4)
    r.skip(WIRE_FIXED64)
    assert_equal(r.pos, 12)
    assert_equal(r.varint(), 7)
    assert_true(r.done())


def test_string_invalid_utf8() raises:
    # A LEN value of one byte 0xff is not valid UTF-8.
    var r = WireReader(from_hex("01ff"))
    var raised = False
    var msg = String()
    try:
        _ = r.string_value()
    except e:
        raised = True
        msg = String(e)
    assert_true(raised, "invalid UTF-8 must raise")
    assert_true("invalid UTF-8" in msg)

    # And it propagates out of a full message decode (string field 14).
    raised = False
    try:
        _ = decode[Scalars](Span(from_hex("7201ff")))
    except:
        raised = True
    assert_true(raised, "invalid UTF-8 in a field must fail decode")


def wrap_layers(payload: Span[Byte, _], layers: Int) raises -> List[Byte]:
    var buf = List[Byte](payload)
    for _ in range(layers):
        var w = WireWriter()
        w.len_prefixed(1, Span(buf))
        buf = w^.take()
    return buf^


def drill(var r: WireReader, remaining: Int) raises:
    if remaining == 0:
        assert_true(r.done())
        return
    var tag = r.read_tag()
    assert_equal(tag[0], 1)
    assert_equal(tag[1], WIRE_LEN)
    var sub = r.sub_reader()
    drill(sub^, remaining - 1)


def test_nesting_depth_limit() raises:
    # Exactly MAX_DECODE_DEPTH nested LEN wrappers decode fine: the
    # innermost sub_reader sits at depth 100.
    var ok = wrap_layers(Span(List[Byte]()), MAX_DECODE_DEPTH)
    drill(WireReader(Span(ok)), MAX_DECODE_DEPTH)

    # One more layer trips the limit on the 101st sub_reader call.
    var deep = wrap_layers(Span(List[Byte]()), MAX_DECODE_DEPTH + 1)
    var raised = False
    var msg = String()
    try:
        drill(WireReader(Span(deep)), MAX_DECODE_DEPTH + 1)
    except e:
        raised = True
        msg = String(e)
    assert_true(raised, "101 layers must raise")
    assert_true("nesting exceeds depth limit" in msg)

    # A reader already at the limit rejects the very next sub_reader.
    var r = WireReader(from_hex("0a00"), depth=MAX_DECODE_DEPTH)
    var tag = r.read_tag()
    assert_equal(tag[1], WIRE_LEN)
    raised = False
    msg = String()
    try:
        _ = r.sub_reader()
    except e:
        raised = True
        msg = String(e)
    assert_true(raised, "sub_reader at depth limit must raise")
    assert_true("nesting exceeds depth limit" in msg)


def test_decode_error_propagation() raises:
    # Field 1 varint whose continuation bit promises more bytes.
    var raised = False
    var msg = String()
    try:
        _ = decode[Scalars](Span(from_hex("0880")))
    except e:
        raised = True
        msg = String(e)
    assert_true(raised, "truncated varint must fail decode")
    assert_true("truncated varint" in msg)


def test_max_field_number() raises:
    # 536870911 == 2^29 - 1, the largest legal field number.
    var w = WireWriter()
    w.tag(536870911, WIRE_VARINT)
    w.varint(1)
    w.tag(536870911, WIRE_FIXED32)
    w.fixed32(2)
    var buf = w^.take()

    var r = WireReader(buf)
    var tag = r.read_tag()
    assert_equal(tag[0], 536870911)
    assert_equal(tag[1], WIRE_VARINT)
    assert_equal(r.varint(), 1)
    tag = r.read_tag()
    assert_equal(tag[0], 536870911)
    assert_equal(tag[1], WIRE_FIXED32)
    assert_equal(r.fixed32(), 2)
    assert_true(r.done())

    # 536870912 is the first field number outside the 29-bit range.
    var above = WireReader(from_hex("8080808010"))
    var raised = False
    var msg = String()
    try:
        _ = above.read_tag()
    except e:
        raised = True
        msg = String(e)
    assert_true(raised, "field number 536870912 must raise")
    assert_true("invalid field number" in msg)


def test_unknown_field_roundtrip() raises:
    # One known field (1) first, then unknown fields of wire types
    # 0, 1, 2, 5 -- field 2048 needs a multi-byte tag.
    var w = WireWriter()
    w.int32(1, 42)
    w.tag(100, WIRE_VARINT)
    w.varint(300)
    w.fixed64_field(101, 0x1122334455667788)
    w.bytes_field(102, Span(from_hex("cafe")))
    w.fixed32_field(2048, 0xCAFEBABE)
    var buf = w^.take()

    var m = decode[Scalars](Span(buf))
    assert_equal(m.f_int32, 42)
    assert_true(len(m._unknown) > 0)
    # Re-encode: field 1 is emitted first, then the captured unknown
    # bytes verbatim -- byte-identical to the input.
    assert_equal(to_hex(encode(m)), to_hex(buf))


def test_merge_two_calls_scalars() raises:
    # Singular scalar last-wins across merges; a field set only in the
    # first merge survives the second.
    var w1 = WireWriter()
    w1.int32(1, 1)
    w1.string_field(14, "keep")
    var b1 = w1^.take()
    var w2 = WireWriter()
    w2.int32(1, 2)
    var b2 = w2^.take()

    var m = Scalars()
    var r1 = WireReader(Span(b1))
    m.merge_from(r1)
    var r2 = WireReader(Span(b2))
    m.merge_from(r2)
    assert_equal(m.f_int32, 2)
    assert_equal(m.f_string, "keep")


def test_merge_two_calls_nested() raises:
    var n1 = Nested()
    var s1 = Scalars()
    s1.f_int32 = 1
    s1.f_string = "keep"
    n1.inner = s1^
    n1.packed_ints = [Int32(1), Int32(2)]
    n1.counts["k"] = 1
    var b1 = encode(n1)

    var n2 = Nested()
    var s2 = Scalars()
    s2.f_int64 = 2
    n2.inner = s2^
    n2.packed_ints = [Int32(3)]
    n2.counts["k"] = 9
    n2.counts["j"] = 2
    var b2 = encode(n2)

    var m = Nested()
    var r1 = WireReader(Span(b1))
    m.merge_from(r1)
    var r2 = WireReader(Span(b2))
    m.merge_from(r2)

    # Repeated fields append across merges.
    assert_equal(len(m.packed_ints), 3)
    assert_equal(m.packed_ints[0], 1)
    assert_equal(m.packed_ints[1], 2)
    assert_equal(m.packed_ints[2], 3)
    # Map keys overwrite; new keys are added.
    assert_equal(len(m.counts), 2)
    assert_equal(m.counts["k"], 9)
    assert_equal(m.counts["j"], 2)
    # Submessages merge field-by-field: values set only in the first
    # occurrence survive, per the protobuf spec (and the generated code).
    assert_true(Bool(m.inner))
    assert_equal(m.inner.value().f_int64, 2)
    assert_equal(m.inner.value().f_int32, 1)
    assert_equal(m.inner.value().f_string, "keep")

    # The protoc-gen-mojo output merges submessages field-level: values
    # set only in the first occurrence survive.
    var g = GenNested()
    var g1 = WireReader(Span(b1))
    g.merge_from(g1)
    var g2 = WireReader(Span(b2))
    g.merge_from(g2)
    assert_true(Bool(g.inner))
    assert_equal(g.inner.value().f_int64, 2)
    assert_equal(g.inner.value().f_int32, 1)
    assert_equal(g.inner.value().f_string, "keep")


def test_duplicate_fields_one_buffer() raises:
    # Duplicate singular scalar within one buffer: last value wins.
    var w = WireWriter()
    w.int32(1, 1)
    w.int32(1, 2)
    var buf = w^.take()
    var m = decode[Scalars](Span(buf))
    assert_equal(m.f_int32, 2)

    # Duplicate submessage occurrences within one buffer.
    var sub1 = WireWriter()
    sub1.int32(1, 7)  # inner.f_int32
    var p1 = sub1^.take()
    var sub2 = WireWriter()
    sub2.string_field(14, "hi")  # inner.f_string
    var p2 = sub2^.take()
    var w2 = WireWriter()
    w2.len_prefixed(1, Span(p1))
    w2.len_prefixed(1, Span(p2))
    var buf2 = w2^.take()

    # Hand-written reference: occurrences merge field-level, like the
    # generated code below.
    var n = decode[Nested](Span(buf2))
    assert_true(Bool(n.inner))
    assert_equal(n.inner.value().f_string, "hi")
    assert_equal(n.inner.value().f_int32, 7)

    # Generated code: occurrences merge field-level (spec behavior).
    var g = decode[GenNested](Span(buf2))
    assert_true(Bool(g.inner))
    assert_equal(g.inner.value().f_string, "hi")
    assert_equal(g.inner.value().f_int32, 7)


def test_oneof_last_wins() raises:
    # as_text then as_num in one buffer: the numeric arm wins.
    var w = WireWriter()
    w.string_field(6, "txt")
    w.int64(7, 5)
    var n = decode[Nested](Span(w^.take()))
    assert_equal(n.choice_case, 7)
    assert_equal(n.as_num, 5)
    assert_equal(n.as_text, "")

    # Reverse order: the text arm wins and clears the number.
    var w2 = WireWriter()
    w2.int64(7, 5)
    w2.string_field(6, "txt")
    var n2 = decode[Nested](Span(w2^.take()))
    assert_equal(n2.choice_case, 6)
    assert_equal(n2.as_text, "txt")
    assert_equal(n2.as_num, 0)


def test_zigzag_extremes() raises:
    assert_equal(zigzag_decode64(UInt64.MAX), Int64.MIN)
    assert_equal(zigzag_decode64(UInt64.MAX - 1), Int64.MAX)
    assert_equal(zigzag_decode32(UInt32(0xFFFFFFFF)), Int32.MIN)
    assert_equal(zigzag_decode32(UInt32(0xFFFFFFFE)), Int32.MAX)


def test_varint_value_masking() raises:
    # uint32_value discards bits above 32: 2^32 + 1 reads back as 1.
    var w = WireWriter()
    w.varint(UInt64(0x100000001))
    var r = WireReader(w^.take())
    assert_equal(r.uint32_value(), 1)

    # int32_value of the raw 5-byte varint 0xFFFFFFFF (not the
    # sign-extended 10-byte form a conforming writer emits): the low 32
    # bits reinterpret as -1, matching reference-parser truncation.
    var r2 = WireReader(from_hex("ffffffff0f"))
    assert_equal(r2.int32_value(), -1)


def test_bool_values() raises:
    # Any nonzero varint is True.
    var r = WireReader(from_hex("02"))
    assert_true(r.bool_value())
    # An overlong (non-canonical) encoding of zero is False.
    var r2 = WireReader(from_hex("8000"))
    assert_false(r2.bool_value())


def check_varint_len(v: UInt64, expected_len: Int) raises:
    var w = WireWriter()
    w.varint(v)
    var buf = w^.take()
    assert_equal(len(buf), expected_len)
    var r = WireReader(buf)
    assert_equal(r.varint(), v)
    assert_true(r.done())


def test_varint_boundaries() raises:
    check_varint_len((UInt64(1) << 28) - 1, 4)
    check_varint_len(UInt64(1) << 28, 5)
    check_varint_len((UInt64(1) << 56) - 1, 8)
    check_varint_len(UInt64(1) << 56, 9)


def test_float_specials() raises:
    var w = WireWriter()
    w.float_field(1, Float32(from_bits=UInt32(0x7F800000)))  # +inf
    w.float_field(2, Float32(from_bits=UInt32(0xFF800000)))  # -inf
    w.float_field(3, Float32(from_bits=UInt32(0x7FC00000)))  # quiet NaN
    w.float_field(4, Float32(-0.0))
    w.double_field(5, Float64(from_bits=UInt64(0x7FF0000000000000)))
    w.double_field(6, Float64(from_bits=UInt64(0x7FF8000000000000)))
    var buf = w^.take()

    var r = WireReader(buf)
    _ = r.read_tag()
    assert_equal(r.fixed32(), 0x7F800000)
    _ = r.read_tag()
    assert_equal(r.fixed32(), 0xFF800000)
    _ = r.read_tag()
    var nan_bits = r.fixed32()
    # NaN: exponent all ones, mantissa nonzero; exact payload preserved.
    assert_equal(nan_bits & 0x7F800000, 0x7F800000)
    assert_true((nan_bits & 0x007FFFFF) != 0)
    assert_equal(nan_bits, 0x7FC00000)
    _ = r.read_tag()
    assert_equal(r.fixed32(), 0x80000000)  # -0.0 keeps its sign bit
    _ = r.read_tag()
    assert_equal(r.fixed64(), 0x7FF0000000000000)
    _ = r.read_tag()
    var dnan_bits = r.fixed64()
    assert_equal(dnan_bits & 0x7FF0000000000000, 0x7FF0000000000000)
    assert_true((dnan_bits & 0x000FFFFFFFFFFFFF) != 0)
    assert_true(r.done())

    # Read side: float_value/double_value reproduce the exact bits.
    var r2 = WireReader(buf)
    _ = r2.read_tag()
    assert_equal(r2.float_value().to_bits(), 0x7F800000)
    _ = r2.read_tag()
    assert_equal(r2.float_value().to_bits(), 0xFF800000)
    _ = r2.read_tag()
    assert_equal(r2.float_value().to_bits(), 0x7FC00000)
    _ = r2.read_tag()
    assert_equal(r2.float_value().to_bits(), 0x80000000)
    _ = r2.read_tag()
    assert_equal(r2.double_value().to_bits(), 0x7FF0000000000000)

    # -0.0 as a bare fixed32 encodes little-endian as 00 00 00 80.
    var w2 = WireWriter()
    w2.fixed32(UInt32(Float32(-0.0).to_bits()))
    assert_equal(to_hex(w2^.take()), "00000080")


def test_len_prefixed_payloads() raises:
    # Empty payload: tag + zero length, nothing else.
    var w = WireWriter()
    w.len_prefixed(1, Span(List[Byte]()))
    var buf = w^.take()
    assert_equal(to_hex(buf), "0a00")
    var r = WireReader(buf)
    _ = r.read_tag()
    assert_equal(len(r.bytes_value()), 0)
    assert_true(r.done())

    # 200-byte payload: the length varint takes 2 bytes (c8 01).
    var payload = List[Byte]()
    for i in range(200):
        payload.append(Byte(i & 0xFF))
    var w2 = WireWriter()
    w2.len_prefixed(2, Span(payload))
    var buf2 = w2^.take()
    assert_equal(len(buf2), 1 + 2 + 200)
    assert_equal(buf2[1], 0xC8)
    assert_equal(buf2[2], 0x01)
    var r2 = WireReader(buf2)
    var tag = r2.read_tag()
    assert_equal(tag[0], 2)
    assert_equal(tag[1], WIRE_LEN)
    var back = r2.bytes_value()
    assert_equal(to_hex(back), to_hex(payload))
    assert_true(r2.done())


def main() raises:
    test_fixed_truncation()
    test_bytes_value_overrun()
    test_skip_unsupported_wire_types()
    test_skip_fixed_advances()
    test_string_invalid_utf8()
    test_nesting_depth_limit()
    test_decode_error_propagation()
    test_max_field_number()
    test_unknown_field_roundtrip()
    test_merge_two_calls_scalars()
    test_merge_two_calls_nested()
    test_duplicate_fields_one_buffer()
    test_oneof_last_wins()
    test_zigzag_extremes()
    test_bool_values()
    test_varint_value_masking()
    test_varint_boundaries()
    test_float_specials()
    test_len_prefixed_payloads()
    print("test_wire_edges: all tests passed")
