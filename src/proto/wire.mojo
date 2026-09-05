# ===----------------------------------------------------------------------=== #
# Copyright (c) 2026 the grpc-mojo contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
# ===----------------------------------------------------------------------=== #

"""Protobuf binary wire-format primitives: `WireWriter` and `WireReader`.

Implements the encoding described in the
[protobuf encoding guide](https://protobuf.dev/programming-guides/encoding/):
base-128 varints, ZigZag transforms for `sint32`/`sint64`, little-endian
fixed32/fixed64, and length-delimited records. Everything here is a pure
function over bytes — no I/O. `WireWriter` appends to an owned `List[Byte]`;
`WireReader` consumes a byte span and validates as it goes (truncation,
overlong varints, invalid field numbers, unsupported group wire types),
enforcing the same nesting-depth limit as reference implementations.

Generated message code (`tools/protoc-gen-mojo`) and hand-written messages
build their `encode_to`/`merge_from` implementations on these primitives;
see `proto.message` for the generic entry points.
"""

comptime WIRE_VARINT = 0
"""Wire type 0: base-128 varint (int32/64, uint32/64, sint32/64, bool, enum)."""
comptime WIRE_FIXED64 = 1
"""Wire type 1: 8-byte little-endian value (fixed64, sfixed64, double)."""
comptime WIRE_LEN = 2
"""Wire type 2: length-delimited (string, bytes, submessage, packed repeated)."""
comptime WIRE_FIXED32 = 5
"""Wire type 5: 4-byte little-endian value (fixed32, sfixed32, float)."""

comptime MAX_VARINT_LEN = 10
"""Maximum encoded size of a varint in bytes (a 64-bit value needs 10)."""

comptime MAX_FIELD_NUMBER = (1 << 29) - 1
"""Largest field number allowed by the protobuf wire format."""

comptime MAX_BYTES_FIELD = 64 * 1024 * 1024
"""Default ceiling for a single length-delimited field, in bytes."""
comptime MAX_DECODE_DEPTH = 100
"""Nested-message depth limit, matching reference implementations."""


def zigzag_encode32(v: Int32) -> UInt32:
    """Maps a signed 32-bit value to an unsigned one with a small varint form.

    ZigZag interleaves negative and positive values (0 -> 0, -1 -> 1,
    1 -> 2, -2 -> 3, ...) so that small-magnitude negatives encode in few
    varint bytes. Used for `sint32` fields.

    Args:
        v: The signed value to transform.

    Returns:
        The ZigZag-encoded unsigned value.
    """
    return UInt32((v << 1) ^ (v >> 31))


def zigzag_decode32(v: UInt32) -> Int32:
    """Reverses the 32-bit ZigZag transform applied by `zigzag_encode32`.

    Args:
        v: The ZigZag-encoded unsigned value.

    Returns:
        The original signed value.
    """
    return Int32(v >> 1) ^ -Int32(v & 1)


def zigzag_encode64(v: Int64) -> UInt64:
    """Maps a signed 64-bit value to an unsigned one with a small varint form.

    64-bit counterpart of `zigzag_encode32`; used for `sint64` fields.

    Args:
        v: The signed value to transform.

    Returns:
        The ZigZag-encoded unsigned value.
    """
    return UInt64((v << 1) ^ (v >> 63))


def zigzag_decode64(v: UInt64) -> Int64:
    """Reverses the 64-bit ZigZag transform applied by `zigzag_encode64`.

    Args:
        v: The ZigZag-encoded unsigned value.

    Returns:
        The original signed value.
    """
    return Int64(v >> 1) ^ -Int64(v & 1)


struct WireWriter(Movable):
    """Appends protobuf wire-format data to a byte buffer.

    The low-level primitives (`varint`, `fixed32`, `fixed64`, `tag`) write
    raw wire elements; the `*_field` helpers write a complete tag + value
    pair for each scalar kind. Callers implement proto3 field-presence
    semantics: default-valued singular fields are skipped by not calling
    the helper at all. Retrieve the finished encoding with `take()`.
    """

    var buf: List[Byte]
    """Accumulated wire-format bytes."""

    def __init__(out self):
        """Creates a writer with an empty buffer."""
        self.buf = List[Byte]()

    def take(deinit self) -> List[Byte]:
        """Consumes the writer and returns the accumulated bytes.

        Returns:
            The encoded buffer, moved out of the writer.
        """
        return self.buf^

    # --- primitives ---

    def varint(mut self, v: UInt64):
        """Appends a base-128 varint: 7 bits per byte, little-endian groups.

        Args:
            v: The value to encode (1 to `MAX_VARINT_LEN` bytes).
        """
        var x = v
        while x >= 0x80:
            self.buf.append(UInt8((x & 0x7F) | 0x80))
            x >>= 7
        self.buf.append(UInt8(x))

    def fixed32(mut self, v: UInt32):
        """Appends 4 bytes, little-endian.

        Args:
            v: The value to encode.
        """
        self.buf.append(UInt8(v & 0xFF))
        self.buf.append(UInt8((v >> 8) & 0xFF))
        self.buf.append(UInt8((v >> 16) & 0xFF))
        self.buf.append(UInt8((v >> 24) & 0xFF))

    def fixed64(mut self, v: UInt64):
        """Appends 8 bytes, little-endian.

        Args:
            v: The value to encode.
        """
        self.fixed32(UInt32(v & 0xFFFFFFFF))
        self.fixed32(UInt32(v >> 32))

    def tag(mut self, field: Int, wire_type: Int):
        """Appends a field tag: the varint `(field << 3) | wire_type`.

        Args:
            field: The field number (must be >= 1).
            wire_type: One of the `WIRE_*` constants.
        """
        self.varint(UInt64((field << 3) | wire_type))

    # --- fields (proto3 semantics: default values are skipped by callers) ---

    def int32(mut self, field: Int, v: Int32):
        """Appends an `int32` field as a tagged varint.

        Negative values are sign-extended to 64 bits on the wire, so they
        always occupy 10 bytes — as required for cross-implementation
        compatibility.

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_VARINT)
        self.varint(UInt64(Int64(v)))

    def int64(mut self, field: Int, v: Int64):
        """Appends an `int64` field as a tagged varint.

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_VARINT)
        self.varint(UInt64(v))

    def uint32(mut self, field: Int, v: UInt32):
        """Appends a `uint32` field as a tagged varint.

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_VARINT)
        # Mask defensively: Mojo 1.0 can fold composed int casts through a
        # signed intermediate, sign-extending values with the high bit set.
        self.varint(UInt64(v) & 0xFFFFFFFF)

    def uint64(mut self, field: Int, v: UInt64):
        """Appends a `uint64` field as a tagged varint.

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_VARINT)
        self.varint(v)

    def sint32(mut self, field: Int, v: Int32):
        """Appends an `sint32` field as a tagged ZigZag varint.

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_VARINT)
        # zigzag64 of the sign-extended value equals zigzag32 for all int32,
        # and avoids a UInt32->UInt64 cast that Mojo 1.0 may fold into a
        # sign-extending cast (observed with composed conversions).
        self.varint(zigzag_encode64(Int64(v)))

    def sint64(mut self, field: Int, v: Int64):
        """Appends an `sint64` field as a tagged ZigZag varint.

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_VARINT)
        self.varint(zigzag_encode64(v))

    def bool_field(mut self, field: Int, v: Bool):
        """Appends a `bool` field as a tagged varint (0 or 1).

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_VARINT)
        self.varint(UInt64(1) if v else UInt64(0))

    def fixed32_field(mut self, field: Int, v: UInt32):
        """Appends a `fixed32` field: tag plus 4 little-endian bytes.

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_FIXED32)
        self.fixed32(v)

    def fixed64_field(mut self, field: Int, v: UInt64):
        """Appends a `fixed64` field: tag plus 8 little-endian bytes.

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_FIXED64)
        self.fixed64(v)

    def sfixed32_field(mut self, field: Int, v: Int32):
        """Appends an `sfixed32` field: tag plus 4 little-endian bytes.

        Args:
            field: The field number.
            v: The field value (two's-complement bit pattern).
        """
        self.fixed32_field(field, UInt32(v))

    def sfixed64_field(mut self, field: Int, v: Int64):
        """Appends an `sfixed64` field: tag plus 8 little-endian bytes.

        Args:
            field: The field number.
            v: The field value (two's-complement bit pattern).
        """
        self.fixed64_field(field, UInt64(v))

    def float_field(mut self, field: Int, v: Float32):
        """Appends a `float` field: tag plus the IEEE 754 bits, little-endian.

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_FIXED32)
        self.fixed32(UInt32(v.to_bits()))

    def double_field(mut self, field: Int, v: Float64):
        """Appends a `double` field: tag plus the IEEE 754 bits, little-endian.

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_FIXED64)
        self.fixed64(UInt64(v.to_bits()))

    def bytes_field(mut self, field: Int, v: Span[Byte, _]):
        """Appends a `bytes` field: tag, varint length, then the raw bytes.

        Args:
            field: The field number.
            v: The field value.
        """
        self.tag(field, WIRE_LEN)
        self.varint(UInt64(len(v)))
        self.buf.extend(v)

    def string_field(mut self, field: Int, v: StringSpan):
        """Appends a `string` field as length-delimited UTF-8 bytes.

        Args:
            field: The field number.
            v: The field value.
        """
        self.bytes_field(field, v.as_bytes())

    def len_prefixed(mut self, field: Int, payload: Span[Byte, _]):
        """Appends an already-encoded submessage or packed repeated field.

        Writes the tag and varint length, then the payload verbatim.

        Args:
            field: The field number.
            payload: The pre-encoded wire bytes of the submessage or packed
                values.
        """
        self.bytes_field(field, payload)


struct WireReader(Movable):
    """Consumes and validates protobuf wire-format data from a byte buffer.

    Rejects malformed input as reference parsers do: truncated values,
    varints longer than 64 bits, field numbers outside the 29-bit range, and
    the legacy group wire types (3 and 4). Nested messages are read through
    `sub_reader()`, which enforces `MAX_DECODE_DEPTH`. Length-delimited
    fields larger than `max_bytes_field` (default `MAX_BYTES_FIELD`) are
    rejected so a hostile length cannot force an oversized allocation.
    Unknown fields can be skipped with `skip()` or preserved byte-for-byte
    with `capture_field()`.
    """

    var data: List[Byte]
    """The wire bytes being decoded (copied from the input span)."""
    var pos: Int
    """Current read offset into `data`."""
    var depth: Int
    """Nesting depth of this reader (0 = top level)."""
    var max_bytes_field: Int
    """Ceiling for one length-delimited field, in bytes."""

    def __init__(
        out self,
        data: Span[Byte, _],
        *,
        depth: Int = 0,
        max_bytes_field: Int = MAX_BYTES_FIELD,
    ):
        """Creates a reader over a copy of the given bytes.

        Args:
            data: The wire-format bytes to decode.
            depth: The nesting depth to start at; leave at 0 except when
                constructing readers for nested messages by hand (prefer
                `sub_reader()`, which tracks depth automatically).
            max_bytes_field: Maximum accepted length-delimited field size.
        """
        self.data = List[Byte](data)
        self.pos = 0
        self.depth = depth
        self.max_bytes_field = max_bytes_field

    def sub_reader(mut self) raises -> WireReader:
        """Consumes a length-delimited field and returns a reader over it.

        The primary way to decode a nested message: reads the varint length
        and value bytes from this reader, then wraps them in a child reader
        one level deeper.

        Returns:
            A reader positioned at the start of the nested message bytes.

        Raises:
            If nesting exceeds `MAX_DECODE_DEPTH` (the recursion limit used
            by reference parsers), or if the length-delimited field is
            truncated or exceeds `max_bytes_field`.
        """
        if self.depth + 1 > MAX_DECODE_DEPTH:
            raise Error("proto: message nesting exceeds depth limit")
        var child = WireReader(
            Span(self.bytes_value()),
            depth=self.depth + 1,
            max_bytes_field=self.max_bytes_field,
        )
        return child^

    def done(self) -> Bool:
        """Reports whether all input has been consumed.

        Returns:
            True when the read position has reached the end of the data.
        """
        return self.pos >= len(self.data)

    def varint(mut self) raises -> UInt64:
        """Reads a base-128 varint.

        A 64-bit value occupies at most 10 bytes. The tenth byte may
        contribute only its least-significant payload bit; leftover
        high bits or a continuation flag are overflow, matching the
        reference parsers.

        Returns:
            The decoded value.

        Raises:
            If the input ends mid-varint or the encoding exceeds 64 bits.
        """
        var result: UInt64 = 0
        var shift = 0
        var count = 0
        while True:
            if self.pos >= len(self.data):
                raise Error("proto: truncated varint")
            var b = self.data[self.pos]
            self.pos += 1
            count += 1
            if count > MAX_VARINT_LEN:
                raise Error("proto: varint too long")
            if count == MAX_VARINT_LEN:
                # 9 * 7 = 63 bits already shifted; only bit 0 of this
                # byte may be set, and it must terminate the varint.
                if (b & 0x7E) != 0 or (b & 0x80) != 0:
                    raise Error("proto: varint overflow")
                result |= UInt64(b & 1) << 63
                return result
            result |= UInt64(b & 0x7F) << UInt64(shift)
            if (b & 0x80) == 0:
                return result
            shift += 7

    def fixed32(mut self) raises -> UInt32:
        """Reads 4 little-endian bytes.

        Returns:
            The decoded value.

        Raises:
            If fewer than 4 bytes remain.
        """
        if self.pos + 4 > len(self.data):
            raise Error("proto: truncated fixed32")
        var v = (
            UInt32(self.data[self.pos])
            | (UInt32(self.data[self.pos + 1]) << 8)
            | (UInt32(self.data[self.pos + 2]) << 16)
            | (UInt32(self.data[self.pos + 3]) << 24)
        )
        self.pos += 4
        return v

    def fixed64(mut self) raises -> UInt64:
        """Reads 8 little-endian bytes.

        Returns:
            The decoded value.

        Raises:
            If fewer than 8 bytes remain.
        """
        var lo = UInt64(self.fixed32())
        var hi = UInt64(self.fixed32())
        return lo | (hi << 32)

    def read_tag(mut self) raises -> Tuple[Int, Int]:
        """Reads a field tag.

        Returns:
            A `(field_number, wire_type)` tuple.

        Raises:
            If the tag varint is malformed or the field number falls outside
            the range 1 through 2^29 - 1.
        """
        var t = self.varint()
        var field = Int(t >> 3)
        var wire_type = Int(t & 0x7)
        if field == 0 or field > MAX_FIELD_NUMBER:
            raise Error("proto: invalid field number")
        return (field, wire_type)

    def bytes_value(mut self) raises -> List[Byte]:
        """Reads a length-delimited value: a varint length, then that many bytes.

        Returns:
            A copy of the value bytes.

        Raises:
            If the declared length runs past the end of the input, or if
            it exceeds `max_bytes_field`.
        """
        var n = Int(self.varint())
        # Compare against the remaining byte count rather than computing
        # `pos + n`, which can overflow Int for hostile 63-bit lengths and
        # slip past the bounds check into a slice crash.
        if n < 0 or n > len(self.data) - self.pos:
            raise Error("proto: truncated length-delimited field")
        if n > self.max_bytes_field:
            raise Error("proto: length-delimited field exceeds size limit")
        var out = List[Byte](self.data[self.pos : self.pos + n])
        self.pos += n
        return out^

    def string_value(mut self) raises -> String:
        """Reads a length-delimited value as a UTF-8 string.

        Returns:
            The decoded string.

        Raises:
            If the field is truncated, exceeds `max_bytes_field`, or the
            bytes are not valid UTF-8.
        """
        return String(from_utf8=self.bytes_value())

    # Typed helpers over varint
    def int32_value(mut self) raises -> Int32:
        """Reads a varint as an `int32` field value.

        Negative values arrive sign-extended to 64 bits on the wire; the
        low 32 bits are reinterpreted as the signed result.

        Returns:
            The decoded value.

        Raises:
            If the varint is truncated or too long.
        """
        return Int32(from_bits=UInt32(self.varint() & 0xFFFFFFFF))

    def int64_value(mut self) raises -> Int64:
        """Reads a varint as an `int64` field value.

        Returns:
            The decoded value.

        Raises:
            If the varint is truncated or too long.
        """
        return Int64(from_bits=self.varint())

    def uint32_value(mut self) raises -> UInt32:
        """Reads a varint as a `uint32` field value (high bits discarded).

        Returns:
            The decoded value.

        Raises:
            If the varint is truncated or too long.
        """
        return UInt32(self.varint() & 0xFFFFFFFF)

    def sint32_value(mut self) raises -> Int32:
        """Reads a ZigZag varint as an `sint32` field value.

        Returns:
            The decoded value.

        Raises:
            If the varint is truncated or too long.
        """
        return zigzag_decode32(UInt32(self.varint() & 0xFFFFFFFF))

    def sint64_value(mut self) raises -> Int64:
        """Reads a ZigZag varint as an `sint64` field value.

        Returns:
            The decoded value.

        Raises:
            If the varint is truncated or too long.
        """
        return zigzag_decode64(self.varint())

    def sfixed32_value(mut self) raises -> Int32:
        """Reads 4 little-endian bytes as an `sfixed32` field value.

        Returns:
            The decoded value.

        Raises:
            If fewer than 4 bytes remain.
        """
        return Int32(from_bits=self.fixed32())

    def sfixed64_value(mut self) raises -> Int64:
        """Reads 8 little-endian bytes as an `sfixed64` field value.

        Returns:
            The decoded value.

        Raises:
            If fewer than 8 bytes remain.
        """
        return Int64(from_bits=self.fixed64())

    def bool_value(mut self) raises -> Bool:
        """Reads a varint as a `bool` field value (any nonzero value is True).

        Returns:
            The decoded value.

        Raises:
            If the varint is truncated or too long.
        """
        return self.varint() != 0

    def float_value(mut self) raises -> Float32:
        """Reads 4 little-endian bytes as an IEEE 754 `float` field value.

        Returns:
            The decoded value.

        Raises:
            If fewer than 4 bytes remain.
        """
        return Float32(from_bits=self.fixed32())

    def double_value(mut self) raises -> Float64:
        """Reads 8 little-endian bytes as an IEEE 754 `double` field value.

        Returns:
            The decoded value.

        Raises:
            If fewer than 8 bytes remain.
        """
        return Float64(from_bits=self.fixed64())

    def capture_field(
        mut self, field: Int, wire_type: Int, mut out_buf: List[Byte]
    ) raises:
        """Skips a field while appending its wire bytes (tag + value) to a buffer.

        Implements unknown-field preservation per the proto3 spec: messages
        re-emit captured bytes on encode so unrecognized fields survive a
        decode/encode round trip.

        Args:
            field: The field number from `read_tag()`.
            wire_type: The wire type from `read_tag()`.
            out_buf: Buffer receiving the re-encoded tag followed by the
                field's value bytes.

        Raises:
            If the field value is malformed or the wire type is unsupported.
        """
        # Re-encode the tag.
        var tag = UInt64((field << 3) | wire_type)
        var t = tag
        while t >= 0x80:
            out_buf.append(UInt8((t & 0x7F) | 0x80))
            t >>= 7
        out_buf.append(UInt8(t))
        var start = self.pos
        self.skip(wire_type)
        out_buf.extend(Span(self.data)[start : self.pos])

    def skip(mut self, wire_type: Int) raises:
        """Skips an unknown field's value.

        Args:
            wire_type: The wire type from `read_tag()`.

        Raises:
            If the value is malformed, or the wire type is the legacy group
            encoding (3 or 4) or otherwise unsupported.
        """
        if wire_type == WIRE_VARINT:
            _ = self.varint()
        elif wire_type == WIRE_FIXED64:
            _ = self.fixed64()
        elif wire_type == WIRE_LEN:
            _ = self.bytes_value()
        elif wire_type == WIRE_FIXED32:
            _ = self.fixed32()
        else:
            # Groups (3/4) are proto1 legacy; we reject them.
            raise Error("proto: unsupported wire type " + String(wire_type))
