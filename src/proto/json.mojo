# ===----------------------------------------------------------------------=== #
# Copyright (c) 2026 the grpc-mojo contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
# ===----------------------------------------------------------------------=== #

"""Strict proto3 JSON support for supported generated flat messages.

The public entry points mirror binary `encode` and `decode`. Generated message
types opt into `ProtoJsonMessage` only when every field has a complete JSON
mapping. This prevents unsupported fields from being dropped at runtime.
"""

from std.base64 import b64decode, b64encode

from .message import ProtoMessage


struct JsonPrintOptions(Copyable):
    """Controls proto3 JSON output.

    All defaults match the protobuf JSON mapping.
    """

    var preserve_proto_field_names: Bool
    """Use original proto field names instead of their JSON names."""
    var always_print_fields_with_no_presence: Bool
    """Print implicit-presence fields even when they hold their defaults."""

    def __init__(
        out self,
        *,
        preserve_proto_field_names: Bool = False,
        always_print_fields_with_no_presence: Bool = False,
    ):
        """Builds print options with protobuf-compatible defaults.

        Args:
            preserve_proto_field_names: Use original proto field names.
            always_print_fields_with_no_presence: Print default-valued
                implicit-presence fields.
        """
        self.preserve_proto_field_names = preserve_proto_field_names
        self.always_print_fields_with_no_presence = (
            always_print_fields_with_no_presence
        )


struct JsonParseOptions(Copyable):
    """Controls proto3 JSON input."""

    var ignore_unknown_fields: Bool
    """Skip unknown fields instead of rejecting them."""
    var max_depth: Int
    """Maximum JSON nesting depth. The protobuf default is 100."""

    def __init__(
        out self,
        *,
        ignore_unknown_fields: Bool = False,
        max_depth: Int = 100,
    ):
        """Builds parse options with protobuf-compatible defaults.

        Args:
            ignore_unknown_fields: Skip fields absent from the schema.
            max_depth: Maximum accepted JSON nesting depth.
        """
        self.ignore_unknown_fields = ignore_unknown_fields
        self.max_depth = max_depth


def _append_ascii(mut out: List[Byte], text: StringSpan):
    out.extend(text.as_bytes())


def _append_hex_escape(mut out: List[Byte], value: UInt8):
    _append_ascii(out, "\\u00")
    comptime digits = "0123456789abcdef"
    out.append(digits.as_bytes()[Int(value >> 4)])
    out.append(digits.as_bytes()[Int(value & 0x0F)])


def _append_quoted(mut out: List[Byte], text: StringSpan):
    out.append(UInt8(0x22))
    for b in text.as_bytes():
        if b == 0x22:
            _append_ascii(out, '\\"')
        elif b == 0x5C:
            _append_ascii(out, "\\\\")
        elif b == 0x08:
            _append_ascii(out, "\\b")
        elif b == 0x0C:
            _append_ascii(out, "\\f")
        elif b == 0x0A:
            _append_ascii(out, "\\n")
        elif b == 0x0D:
            _append_ascii(out, "\\r")
        elif b == 0x09:
            _append_ascii(out, "\\t")
        elif b < 0x20:
            _append_hex_escape(out, b)
        else:
            out.append(b)
    out.append(UInt8(0x22))


def _float32_is_nan(value: Float32) -> Bool:
    var bits = UInt32(value.to_bits())
    return (bits & 0x7F800000) == 0x7F800000 and (bits & 0x007FFFFF) != 0


def _float32_is_inf(value: Float32) -> Bool:
    return (UInt32(value.to_bits()) & 0x7FFFFFFF) == 0x7F800000


def _float64_is_nan(value: Float64) -> Bool:
    var bits = UInt64(value.to_bits())
    return (bits & 0x7FF0000000000000) == 0x7FF0000000000000 and (
        bits & 0x000FFFFFFFFFFFFF
    ) != 0


def _float64_is_inf(value: Float64) -> Bool:
    return (UInt64(value.to_bits()) & 0x7FFFFFFFFFFFFFFF) == 0x7FF0000000000000


struct ProtoJsonWriter(Movable):
    """Streaming JSON writer used by generated message implementations."""

    var options: JsonPrintOptions
    """The active print options."""
    var _buf: List[Byte]
    var _first_field: Bool

    def __init__(out self, options: JsonPrintOptions = JsonPrintOptions()):
        """Creates an empty writer.

        Args:
            options: Active proto3 JSON print options.
        """
        self.options = options.copy()
        self._buf = List[Byte]()
        self._first_field = True

    def begin_object(mut self):
        """Starts the message object."""
        self._buf.append(UInt8(0x7B))
        self._first_field = True

    def end_object(mut self):
        """Ends the message object."""
        self._buf.append(UInt8(0x7D))

    def field(mut self, json_name: StringSpan, proto_name: StringSpan):
        """Writes a field name and prepares for its value.

        Args:
            json_name: Descriptor JSON name.
            proto_name: Original name in the proto schema.
        """
        if not self._first_field:
            self._buf.append(UInt8(0x2C))
        self._first_field = False
        if self.options.preserve_proto_field_names:
            _append_quoted(self._buf, proto_name)
        else:
            _append_quoted(self._buf, json_name)
        self._buf.append(UInt8(0x3A))

    def int32_value(mut self, value: Int32):
        """Writes a signed 32-bit JSON number.

        Args:
            value: Value to write.
        """
        self._buf.extend(String(value).as_bytes())

    def int64_value(mut self, value: Int64):
        """Writes a signed 64-bit integer as a decimal JSON string.

        Args:
            value: Value to write.
        """
        _append_quoted(self._buf, String(value))

    def uint32_value(mut self, value: UInt32):
        """Writes an unsigned 32-bit JSON number.

        Args:
            value: Value to write.
        """
        self._buf.extend(String(value).as_bytes())

    def uint64_value(mut self, value: UInt64):
        """Writes an unsigned 64-bit integer as a decimal JSON string.

        Args:
            value: Value to write.
        """
        _append_quoted(self._buf, String(value))

    def bool_value(mut self, value: Bool):
        """Writes a JSON boolean.

        Args:
            value: Value to write.
        """
        _append_ascii(self._buf, "true" if value else "false")

    def float32_value(mut self, value: Float32):
        """Writes a protobuf float JSON value.

        Args:
            value: Value to write.
        """
        if _float32_is_nan(value):
            _append_ascii(self._buf, '"NaN"')
        elif _float32_is_inf(value):
            if UInt32(value.to_bits()) >> 31:
                _append_ascii(self._buf, '"-Infinity"')
            else:
                _append_ascii(self._buf, '"Infinity"')
        else:
            self._buf.extend(String(value).as_bytes())

    def float64_value(mut self, value: Float64):
        """Writes a protobuf double JSON value.

        Args:
            value: Value to write.
        """
        if _float64_is_nan(value):
            _append_ascii(self._buf, '"NaN"')
        elif _float64_is_inf(value):
            if UInt64(value.to_bits()) >> 63:
                _append_ascii(self._buf, '"-Infinity"')
            else:
                _append_ascii(self._buf, '"Infinity"')
        else:
            self._buf.extend(String(value).as_bytes())

    def string_value(mut self, value: StringSpan):
        """Writes a JSON string.

        Args:
            value: Value to write.
        """
        _append_quoted(self._buf, value)

    def bytes_value(mut self, value: Span[Byte, _]):
        """Writes bytes using standard padded base64.

        Args:
            value: Bytes to write.
        """
        _append_quoted(self._buf, b64encode(value))

    def take(mut self) raises -> String:
        """Returns the completed UTF-8 JSON text.

        Returns:
            The complete JSON value.

        Raises:
            Error: If the buffered output is not valid UTF-8.
        """
        return String(from_utf8=self._buf)


def _hex_value(b: UInt8) -> Int:
    if b >= 0x30 and b <= 0x39:
        return Int(b - 0x30)
    if b >= 0x41 and b <= 0x46:
        return Int(b - 0x41) + 10
    if b >= 0x61 and b <= 0x66:
        return Int(b - 0x61) + 10
    return -1


def _append_codepoint(mut out: List[Byte], cp: UInt32) raises:
    if cp <= 0x7F:
        out.append(UInt8(cp))
    elif cp <= 0x7FF:
        out.append(UInt8(0xC0 | (cp >> 6)))
        out.append(UInt8(0x80 | (cp & 0x3F)))
    elif cp <= 0xFFFF:
        if cp >= 0xD800 and cp <= 0xDFFF:
            raise Error("proto json: unpaired Unicode surrogate")
        out.append(UInt8(0xE0 | (cp >> 12)))
        out.append(UInt8(0x80 | ((cp >> 6) & 0x3F)))
        out.append(UInt8(0x80 | (cp & 0x3F)))
    elif cp <= 0x10FFFF:
        out.append(UInt8(0xF0 | (cp >> 18)))
        out.append(UInt8(0x80 | ((cp >> 12) & 0x3F)))
        out.append(UInt8(0x80 | ((cp >> 6) & 0x3F)))
        out.append(UInt8(0x80 | (cp & 0x3F)))
    else:
        raise Error("proto json: invalid Unicode code point")


struct ProtoJsonReader(Movable):
    """Strict streaming JSON reader used by generated message code."""

    var options: JsonParseOptions
    """The active parse options."""
    var _data: List[Byte]
    var _pos: Int
    var _first_field: Bool

    def __init__(
        out self,
        text: StringSpan,
        options: JsonParseOptions = JsonParseOptions(),
    ):
        """Creates a reader over one complete JSON value.

        Args:
            text: JSON text to parse.
            options: Active proto3 JSON parse options.
        """
        self.options = options.copy()
        self._data = List[Byte]()
        self._data.extend(text.as_bytes())
        self._pos = 0
        self._first_field = True

    def _skip_ws(mut self):
        while self._pos < len(self._data):
            var b = self._data[self._pos]
            if b != 0x20 and b != 0x09 and b != 0x0A and b != 0x0D:
                return
            self._pos += 1

    def _consume(mut self, expected: UInt8) raises:
        self._skip_ws()
        if self._pos >= len(self._data) or self._data[self._pos] != expected:
            raise Error("proto json: unexpected token")
        self._pos += 1

    def _matches(self, text: StringSpan) -> Bool:
        var bytes = text.as_bytes()
        if self._pos + len(bytes) > len(self._data):
            return False
        for i in range(len(bytes)):
            if self._data[self._pos + i] != bytes[i]:
                return False
        return True

    def _literal(mut self, text: StringSpan) raises:
        self._skip_ws()
        if not self._matches(text):
            raise Error("proto json: invalid literal")
        self._pos += len(text.as_bytes())

    def _unicode_escape(mut self) raises -> UInt32:
        if self._pos + 4 > len(self._data):
            raise Error("proto json: truncated Unicode escape")
        var cp = UInt32(0)
        for _ in range(4):
            var digit = _hex_value(self._data[self._pos])
            if digit < 0:
                raise Error("proto json: invalid Unicode escape")
            cp = (cp << 4) | UInt32(digit)
            self._pos += 1
        return cp

    def string_value(mut self) raises -> String:
        """Reads and unescapes one JSON string.

        Returns:
            The decoded UTF-8 string.

        Raises:
            Error: If the next value is not a valid JSON string.
        """
        self._skip_ws()
        if self._pos >= len(self._data) or self._data[self._pos] != 0x22:
            raise Error("proto json: expected string")
        self._pos += 1
        var out = List[Byte]()
        while self._pos < len(self._data):
            var b = self._data[self._pos]
            self._pos += 1
            if b == 0x22:
                return String(from_utf8=out)
            if b < 0x20:
                raise Error("proto json: unescaped control character")
            if b != 0x5C:
                out.append(b)
                continue
            if self._pos >= len(self._data):
                raise Error("proto json: truncated escape")
            var esc = self._data[self._pos]
            self._pos += 1
            if esc == 0x22 or esc == 0x5C or esc == 0x2F:
                out.append(esc)
            elif esc == 0x62:
                out.append(UInt8(0x08))
            elif esc == 0x66:
                out.append(UInt8(0x0C))
            elif esc == 0x6E:
                out.append(UInt8(0x0A))
            elif esc == 0x72:
                out.append(UInt8(0x0D))
            elif esc == 0x74:
                out.append(UInt8(0x09))
            elif esc == 0x75:
                var cp = self._unicode_escape()
                if cp >= 0xD800 and cp <= 0xDBFF:
                    if (
                        self._pos + 2 > len(self._data)
                        or self._data[self._pos] != 0x5C
                        or self._data[self._pos + 1] != 0x75
                    ):
                        raise Error("proto json: unpaired Unicode surrogate")
                    self._pos += 2
                    var low = self._unicode_escape()
                    if low < 0xDC00 or low > 0xDFFF:
                        raise Error("proto json: unpaired Unicode surrogate")
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00)
                elif cp >= 0xDC00 and cp <= 0xDFFF:
                    raise Error("proto json: unpaired Unicode surrogate")
                _append_codepoint(out, cp)
            else:
                raise Error("proto json: invalid escape")
        raise Error("proto json: unterminated string")

    def enum_name(mut self) raises -> Optional[String]:
        """Reads an enum name when the next JSON value is a string.

        Returns:
            The decoded enum name, or none when the value is numeric.

        Raises:
            Error: If a string value is malformed.
        """
        self._skip_ws()
        if self._pos < len(self._data) and self._data[self._pos] == 0x22:
            return self.string_value()
        return None

    def begin_object(mut self) raises:
        """Starts reading a message object.

        Raises:
            Error: If the input is not an object or exceeds the depth limit.
        """
        if self.options.max_depth < 1:
            raise Error("proto json: maximum nesting depth exceeded")
        self._consume(UInt8(0x7B))
        self._first_field = True

    def next_field(mut self) raises -> Optional[String]:
        """Returns the next field name, or none at the object end.

        Returns:
            The decoded field name, or none after the closing brace.

        Raises:
            Error: If the object syntax or field name is malformed.
        """
        self._skip_ws()
        if self._first_field:
            self._first_field = False
            if self._pos < len(self._data) and self._data[self._pos] == 0x7D:
                self._pos += 1
                return None
        else:
            if self._pos < len(self._data) and self._data[self._pos] == 0x7D:
                self._pos += 1
                return None
            self._consume(UInt8(0x2C))
            self._skip_ws()
            if self._pos < len(self._data) and self._data[self._pos] == 0x7D:
                raise Error("proto json: trailing comma")
        var name = self.string_value()
        self._consume(UInt8(0x3A))
        return name^

    def read_null(mut self) -> Bool:
        """Consumes JSON null when it is the next value.

        Returns:
            True when null was consumed, otherwise false.
        """
        self._skip_ws()
        if self._matches("null"):
            self._pos += 4
            return True
        return False

    def bool_value(mut self) raises -> Bool:
        """Reads a JSON boolean.

        Returns:
            The decoded boolean.

        Raises:
            Error: If the next value is not `true` or `false`.
        """
        self._skip_ws()
        if self._matches("true"):
            self._pos += 4
            return True
        if self._matches("false"):
            self._pos += 5
            return False
        raise Error("proto json: expected boolean")

    def _number_token(mut self) raises -> String:
        self._skip_ws()
        var start = self._pos
        if self._pos < len(self._data) and self._data[self._pos] == 0x2D:
            self._pos += 1
        if self._pos >= len(self._data):
            raise Error("proto json: invalid number")
        if self._data[self._pos] == 0x30:
            self._pos += 1
            if (
                self._pos < len(self._data)
                and self._data[self._pos] >= 0x30
                and self._data[self._pos] <= 0x39
            ):
                raise Error("proto json: leading zero")
        elif self._data[self._pos] >= 0x31 and self._data[self._pos] <= 0x39:
            while (
                self._pos < len(self._data)
                and self._data[self._pos] >= 0x30
                and self._data[self._pos] <= 0x39
            ):
                self._pos += 1
        else:
            raise Error("proto json: invalid number")
        if self._pos < len(self._data) and self._data[self._pos] == 0x2E:
            self._pos += 1
            var frac_start = self._pos
            while (
                self._pos < len(self._data)
                and self._data[self._pos] >= 0x30
                and self._data[self._pos] <= 0x39
            ):
                self._pos += 1
            if self._pos == frac_start:
                raise Error("proto json: invalid fraction")
        if self._pos < len(self._data) and (
            self._data[self._pos] == 0x65 or self._data[self._pos] == 0x45
        ):
            self._pos += 1
            if self._pos < len(self._data) and (
                self._data[self._pos] == 0x2B or self._data[self._pos] == 0x2D
            ):
                self._pos += 1
            var exp_start = self._pos
            while (
                self._pos < len(self._data)
                and self._data[self._pos] >= 0x30
                and self._data[self._pos] <= 0x39
            ):
                self._pos += 1
            if self._pos == exp_start:
                raise Error("proto json: invalid exponent")
        var token = List[Byte]()
        token.extend(Span(self._data)[start : self._pos])
        return String(from_utf8=token)

    def _numeric_text(mut self) raises -> String:
        self._skip_ws()
        if self._pos < len(self._data) and self._data[self._pos] == 0x22:
            var value = self.string_value()
            var probe = ProtoJsonReader(value)
            var token = probe._number_token()
            if token.byte_length() != value.byte_length():
                raise Error("proto json: invalid quoted number")
            return token^
        return self._number_token()

    def _integer_parts(mut self) raises -> Tuple[Bool, List[Byte], Int]:
        # Keep decimal digits exact. Parsing through Float64 would corrupt
        # valid 64-bit values above its integer precision.
        var token = self._numeric_text()
        var src = token.as_bytes()
        var pos = 0
        var negative = False
        if src[pos] == 0x2D:
            negative = True
            pos += 1
        var digits = List[Byte]()
        var fraction_digits = 0
        var after_point = False
        while pos < len(src) and src[pos] != 0x65 and src[pos] != 0x45:
            if src[pos] == 0x2E:
                after_point = True
            else:
                digits.append(src[pos])
                if after_point:
                    fraction_digits += 1
            pos += 1
        var exponent = 0
        if pos < len(src):
            pos += 1
            var exponent_negative = False
            if src[pos] == 0x2B or src[pos] == 0x2D:
                exponent_negative = src[pos] == 0x2D
                pos += 1
            while pos < len(src):
                if exponent < 100000:
                    exponent = exponent * 10 + Int(src[pos] - 0x30)
                pos += 1
            if exponent_negative:
                exponent = -exponent
        return negative, digits^, exponent - fraction_digits

    def _integer_magnitude(
        mut self, maximum: UInt64
    ) raises -> Tuple[Bool, UInt64]:
        var parts = self._integer_parts()
        var negative = parts[0]
        var digits = parts[1].copy()
        var scale = parts[2]
        var first_digit = 0
        while first_digit + 1 < len(digits) and digits[first_digit] == 0x30:
            first_digit += 1
        # Apply the decimal point and exponent by removing required trailing
        # zeros or appending zeros. Any remaining fraction is invalid.
        if scale < 0:
            var remove = -scale
            if remove > len(digits) - first_digit:
                for i in range(first_digit, len(digits)):
                    if digits[i] != 0x30:
                        raise Error("proto json: expected an integer")
                return negative, UInt64(0)
            for i in range(remove):
                if digits[len(digits) - 1 - i] != 0x30:
                    raise Error("proto json: expected an integer")
            for _ in range(remove):
                _ = digits.pop()
            scale = 0
        if len(digits) == 0:
            digits.append(UInt8(0x30))
        var all_zero = True
        for i in range(first_digit, len(digits)):
            if digits[i] != 0x30:
                all_zero = False
                break
        if all_zero:
            return negative, UInt64(0)
        if scale > 20:
            raise Error("proto json: integer out of range")
        var magnitude = UInt64(0)
        for i in range(first_digit, len(digits)):
            var b = digits[i]
            var digit = UInt64(b - 0x30)
            if magnitude > (maximum - digit) // 10:
                raise Error("proto json: integer out of range")
            magnitude = magnitude * 10 + digit
        for _ in range(scale):
            if magnitude > maximum // 10:
                raise Error("proto json: integer out of range")
            magnitude *= 10
        return negative, magnitude

    def int64_value(mut self) raises -> Int64:
        """Reads an exact signed 64-bit protobuf JSON integer.

        Returns:
            The decoded integer.

        Raises:
            Error: If the value is malformed, fractional, or out of range.
        """
        var parsed = self._integer_magnitude(UInt64(0x8000000000000000))
        if parsed[0]:
            if parsed[1] == UInt64(0x8000000000000000):
                return Int64(from_bits=parsed[1])
            return -Int64(parsed[1])
        if parsed[1] > UInt64(0x7FFFFFFFFFFFFFFF):
            raise Error("proto json: integer out of range")
        return Int64(parsed[1])

    def uint64_value(mut self) raises -> UInt64:
        """Reads an exact unsigned 64-bit protobuf JSON integer.

        Returns:
            The decoded integer.

        Raises:
            Error: If the value is malformed, negative, or out of range.
        """
        var parsed = self._integer_magnitude(UInt64(0xFFFFFFFFFFFFFFFF))
        if parsed[0] and parsed[1] != 0:
            raise Error("proto json: unsigned integer cannot be negative")
        return parsed[1]

    def int32_value(mut self) raises -> Int32:
        """Reads an exact signed 32-bit protobuf JSON integer.

        Returns:
            The decoded integer.

        Raises:
            Error: If the value is malformed, fractional, or out of range.
        """
        var value = self.int64_value()
        if value < -2147483648 or value > 2147483647:
            raise Error("proto json: integer out of range")
        return Int32(value)

    def uint32_value(mut self) raises -> UInt32:
        """Reads an exact unsigned 32-bit protobuf JSON integer.

        Returns:
            The decoded integer.

        Raises:
            Error: If the value is malformed, negative, or out of range.
        """
        var value = self.uint64_value()
        if value > 4294967295:
            raise Error("proto json: integer out of range")
        return UInt32(value)

    def float64_value(mut self) raises -> Float64:
        """Reads a protobuf double JSON value.

        Returns:
            The decoded value.

        Raises:
            Error: If the value is malformed or out of range.
        """
        self._skip_ws()
        if self._pos < len(self._data) and self._data[self._pos] == 0x22:
            var text = self.string_value()
            if text == "NaN":
                return Float64(from_bits=UInt64(0x7FF8000000000000))
            if text == "Infinity":
                return Float64(from_bits=UInt64(0x7FF0000000000000))
            if text == "-Infinity":
                return Float64(from_bits=UInt64(0xFFF0000000000000))
            var probe = ProtoJsonReader(text)
            var token = probe._number_token()
            if token.byte_length() != text.byte_length():
                raise Error("proto json: invalid quoted number")
            var value = Float64(token)
            if _float64_is_inf(value):
                raise Error("proto json: floating-point value out of range")
            return value
        var token = self._number_token()
        var value = Float64(token)
        if _float64_is_inf(value):
            raise Error("proto json: floating-point value out of range")
        return value

    def float32_value(mut self) raises -> Float32:
        """Reads a protobuf float JSON value.

        Returns:
            The decoded value.

        Raises:
            Error: If the value is malformed or out of range.
        """
        var value = self.float64_value()
        if _float64_is_nan(value):
            return Float32(from_bits=UInt32(0x7FC00000))
        if _float64_is_inf(value):
            if UInt64(value.to_bits()) >> 63:
                return Float32(from_bits=UInt32(0xFF800000))
            return Float32(from_bits=UInt32(0x7F800000))
        var narrowed = Float32(value)
        if _float32_is_inf(narrowed):
            raise Error("proto json: floating-point value out of range")
        return narrowed

    def bytes_value(mut self) raises -> List[Byte]:
        """Reads standard or URL-safe padded or unpadded base64.

        Returns:
            The decoded bytes.

        Raises:
            Error: If the next value is not valid protobuf JSON base64.
        """
        var text = self.string_value()
        var src = text.as_bytes()
        if len(src) % 4 == 1:
            raise Error("proto json: invalid base64 length")
        var normalized = List[Byte]()
        var padding = 0
        for i in range(len(src)):
            var b = src[i]
            if b == 0x3D:
                padding += 1
                if i < len(src) - 2 or padding > 2:
                    raise Error("proto json: invalid base64 padding")
                normalized.append(b)
            elif padding != 0:
                raise Error("proto json: invalid base64 padding")
            elif (
                (b >= 0x41 and b <= 0x5A)
                or (b >= 0x61 and b <= 0x7A)
                or (b >= 0x30 and b <= 0x39)
                or b == 0x2B
                or b == 0x2F
            ):
                normalized.append(b)
            elif b == 0x2D:
                normalized.append(UInt8(0x2B))
            elif b == 0x5F:
                normalized.append(UInt8(0x2F))
            else:
                raise Error("proto json: invalid base64 character")
        if padding != 0 and len(normalized) % 4 != 0:
            raise Error("proto json: invalid base64 padding")
        while len(normalized) % 4 != 0:
            normalized.append(UInt8(0x3D))
        return b64decode(String(from_utf8=normalized))

    def skip_unknown_value(mut self) raises:
        """Skips one unknown field value when configured to do so.

        Raises:
            Error: If unknown fields are disabled or the value is malformed.
        """
        if not self.options.ignore_unknown_fields:
            raise Error("proto json: unknown field")
        self._skip_value(1)

    def _skip_value(mut self, depth: Int) raises:
        self._skip_ws()
        if self._pos >= len(self._data):
            raise Error("proto json: missing value")
        var b = self._data[self._pos]
        if b == 0x22:
            _ = self.string_value()
            return
        if b == 0x7B:
            if depth >= self.options.max_depth:
                raise Error("proto json: maximum nesting depth exceeded")
            self._pos += 1
            self._skip_ws()
            if self._pos < len(self._data) and self._data[self._pos] == 0x7D:
                self._pos += 1
                return
            while True:
                _ = self.string_value()
                self._consume(UInt8(0x3A))
                self._skip_value(depth + 1)
                self._skip_ws()
                if (
                    self._pos < len(self._data)
                    and self._data[self._pos] == 0x7D
                ):
                    self._pos += 1
                    return
                self._consume(UInt8(0x2C))
                self._skip_ws()
                if (
                    self._pos < len(self._data)
                    and self._data[self._pos] == 0x7D
                ):
                    raise Error("proto json: trailing comma")
        if b == 0x5B:
            if depth >= self.options.max_depth:
                raise Error("proto json: maximum nesting depth exceeded")
            self._pos += 1
            self._skip_ws()
            if self._pos < len(self._data) and self._data[self._pos] == 0x5D:
                self._pos += 1
                return
            while True:
                self._skip_value(depth + 1)
                self._skip_ws()
                if (
                    self._pos < len(self._data)
                    and self._data[self._pos] == 0x5D
                ):
                    self._pos += 1
                    return
                self._consume(UInt8(0x2C))
                self._skip_ws()
                if (
                    self._pos < len(self._data)
                    and self._data[self._pos] == 0x5D
                ):
                    raise Error("proto json: trailing comma")
        if b == 0x74:
            self._literal("true")
            return
        if b == 0x66:
            self._literal("false")
            return
        if b == 0x6E:
            self._literal("null")
            return
        _ = self._number_token()

    def finish(mut self) raises:
        """Rejects trailing content after the message object.

        Raises:
            Error: If non-whitespace input follows the message.
        """
        self._skip_ws()
        if self._pos != len(self._data):
            raise Error("proto json: trailing content")


trait ProtoJsonMessage(ProtoMessage):
    """A protobuf message with a complete proto3 JSON mapping."""

    def encode_json_to(self, mut writer: ProtoJsonWriter) raises:
        """Writes this message as one JSON value.

        Args:
            writer: Destination JSON writer.

        Raises:
            Error: If the message cannot be written as valid JSON.
        """
        ...

    def merge_json_from(mut self, mut reader: ProtoJsonReader) raises:
        """Merges one JSON value into this message.

        Args:
            reader: Source JSON reader.

        Raises:
            Error: If the input is not valid proto3 JSON for this message.
        """
        ...


def encode_json[
    M: ProtoJsonMessage
](msg: M, *, options: JsonPrintOptions = JsonPrintOptions(),) raises -> String:
    """Serializes a supported message using the proto3 JSON mapping.

    Parameters:
        M: A message type with a complete generated JSON mapping.

    Args:
        msg: Message to serialize.
        options: Print options.

    Returns:
        The encoded JSON object.

    Raises:
        Error: If the message cannot be represented as valid JSON.
    """
    var writer = ProtoJsonWriter(options)
    msg.encode_json_to(writer)
    return writer.take()


def decode_json[
    M: ProtoJsonMessage
](
    text: StringSpan,
    *,
    options: JsonParseOptions = JsonParseOptions(),
) raises -> M:
    """Parses one supported message from strict proto3 JSON text.

    Parameters:
        M: A message type with a complete generated JSON mapping.

    Args:
        text: One complete JSON object.
        options: Parse options.

    Returns:
        The decoded message.

    Raises:
        Error: If the input is malformed or violates the message mapping.
    """
    var reader = ProtoJsonReader(text, options)
    var message = M()
    message.merge_json_from(reader)
    reader.finish()
    return message^
