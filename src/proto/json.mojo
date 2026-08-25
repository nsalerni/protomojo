# ===----------------------------------------------------------------------=== #
# Copyright (c) 2026 the grpc-mojo contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
# ===----------------------------------------------------------------------=== #

"""Strict proto3 JSON support for supported generated messages.

The public entry points mirror binary `encode` and `decode`. Generated message
types opt into `ProtoJsonMessage` only when every field has a complete JSON
mapping. This prevents unsupported fields from being dropped at runtime.
"""

from std.base64 import b64decode, b64encode

from .message import ProtoMessage, decode, encode


struct AnyJsonPayload(Movable):
    """Resolved JSON payload for one `google.protobuf.Any` value."""

    var json: String
    """JSON for the embedded message, without the Any envelope."""
    var uses_value_field: Bool
    """Whether the Any envelope stores the payload under `value`."""

    def __init__(
        out self, json: String, *, uses_value_field: Bool = False
    ):
        """Creates a resolved Any payload.

        Args:
            json: Embedded message JSON.
            uses_value_field: Whether to use the well-known `value` form.
        """
        self.json = json
        self.uses_value_field = uses_value_field


struct ProtoJsonTypeResolver(Copyable):
    """Static callbacks used to resolve Any type URLs.

    Generated resolver modules provide these callbacks. The runtime never
    fetches a type URL or guesses an embedded schema.
    """

    var print_any: Optional[
        def(String, List[Byte], Bool, Bool) raises thin -> AnyJsonPayload
    ]
    """Decodes Any bytes and returns their embedded JSON mapping."""
    var parse_any: Optional[
        def(String, String, Bool, Int) raises thin -> List[Byte]
    ]
    """Parses an Any JSON object and returns embedded wire bytes."""

    def __init__(out self):
        """Creates an empty resolver that rejects non-empty Any values."""
        self.print_any = None
        self.parse_any = None

    def __init__(
        out self,
        print_any: def(
            String, List[Byte], Bool, Bool
        ) raises thin -> AnyJsonPayload,
        parse_any: def(
            String, String, Bool, Int
        ) raises thin -> List[Byte],
    ):
        """Creates a resolver from static print and parse callbacks.

        Args:
            print_any: Callback for binary-to-JSON conversion.
            parse_any: Callback for JSON-to-binary conversion.
        """
        self.print_any = print_any
        self.parse_any = parse_any


struct JsonPrintOptions(Copyable):
    """Controls proto3 JSON output.

    All defaults match the protobuf JSON mapping.
    """

    var preserve_proto_field_names: Bool
    """Use original proto field names instead of their JSON names."""
    var always_print_fields_with_no_presence: Bool
    """Print implicit-presence fields even when they hold their defaults."""
    var type_resolver: ProtoJsonTypeResolver
    """Resolves type URLs found in `google.protobuf.Any` values."""

    def __init__(
        out self,
        *,
        preserve_proto_field_names: Bool = False,
        always_print_fields_with_no_presence: Bool = False,
        type_resolver: ProtoJsonTypeResolver = ProtoJsonTypeResolver(),
    ):
        """Builds print options with protobuf-compatible defaults.

        Args:
            preserve_proto_field_names: Use original proto field names.
            always_print_fields_with_no_presence: Print default-valued
                implicit-presence fields.
            type_resolver: Resolver for Any values.
        """
        self.preserve_proto_field_names = preserve_proto_field_names
        self.always_print_fields_with_no_presence = (
            always_print_fields_with_no_presence
        )
        self.type_resolver = type_resolver.copy()


struct JsonParseOptions(Copyable):
    """Controls proto3 JSON input."""

    var ignore_unknown_fields: Bool
    """Skip unknown fields instead of rejecting them."""
    var max_depth: Int
    """Maximum JSON nesting depth. The protobuf default is 100."""
    var type_resolver: ProtoJsonTypeResolver
    """Resolves type URLs found in `google.protobuf.Any` values."""

    def __init__(
        out self,
        *,
        ignore_unknown_fields: Bool = False,
        max_depth: Int = 100,
        type_resolver: ProtoJsonTypeResolver = ProtoJsonTypeResolver(),
    ):
        """Builds parse options with protobuf-compatible defaults.

        Args:
            ignore_unknown_fields: Skip fields absent from the schema.
            max_depth: Maximum accepted JSON nesting depth.
            type_resolver: Resolver for Any values.
        """
        self.ignore_unknown_fields = ignore_unknown_fields
        self.max_depth = max_depth
        self.type_resolver = type_resolver.copy()


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


def _append_padded_decimal(
    mut out: List[Byte], value: Int, width: Int
):
    var text = String(value)
    for _ in range(width - text.byte_length()):
        out.append(UInt8(0x30))
    out.extend(text.as_bytes())


def _is_leap_year(year: Int) -> Bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_in_month(year: Int, month: Int) -> Int:
    if month == 2:
        return 29 if _is_leap_year(year) else 28
    if month == 4 or month == 6 or month == 9 or month == 11:
        return 30
    return 31


def _days_before_month(year: Int, month: Int) -> Int:
    var days = (367 * month - 362) // 12
    if month > 2:
        days -= 1 if _is_leap_year(year) else 2
    return days


def _epoch_days_from_civil(year: Int, month: Int, day: Int) -> Int64:
    var prior_year = year - 1
    var days = (
        365 * prior_year
        + prior_year // 4
        - prior_year // 100
        + prior_year // 400
        + _days_before_month(year, month)
        + day
        - 1
    )
    return Int64(days - 719162)


def _civil_from_epoch_days(days: Int64) -> Tuple[Int, Int, Int]:
    var shifted = days + 719468
    var era = shifted // 146097
    var day_of_era = shifted - era * 146097
    var year_of_era = (
        day_of_era
        - day_of_era // 1460
        + day_of_era // 36524
        - day_of_era // 146096
    ) // 365
    var year = year_of_era + era * 400
    var day_of_year = day_of_era - (
        365 * year_of_era + year_of_era // 4 - year_of_era // 100
    )
    var month_prime = (5 * day_of_year + 2) // 153
    var day = day_of_year - (153 * month_prime + 2) // 5 + 1
    var month = month_prime + Int64(3 if month_prime < 10 else -9)
    year += Int64(1 if month <= 2 else 0)
    return Int(year), Int(month), Int(day)


def _decimal_at(data: Span[Byte, _], start: Int, width: Int) raises -> Int:
    var value = 0
    for offset in range(width):
        var digit = data[start + offset]
        if digit < 0x30 or digit > 0x39:
            raise Error("proto json: invalid timestamp digit")
        value = value * 10 + Int(digit - 0x30)
    return value


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
    var _array_parent_first: Bool
    var _in_array: Bool
    var _map_parent_first: Bool
    var _in_map: Bool

    def __init__(out self, options: JsonPrintOptions = JsonPrintOptions()):
        """Creates an empty writer.

        Args:
            options: Active proto3 JSON print options.
        """
        self.options = options.copy()
        self._buf = List[Byte]()
        self._first_field = True
        self._array_parent_first = True
        self._in_array = False
        self._map_parent_first = True
        self._in_map = False

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

    def begin_map(mut self) raises:
        """Starts a protobuf map object.

        Raises:
            Error: If another map or repeated field value is still open.
        """
        if self._in_map or self._in_array:
            raise Error("proto json: nested map writer state")
        self._buf.append(UInt8(0x7B))
        self._map_parent_first = self._first_field
        self._first_field = True
        self._in_map = True

    def map_key(mut self, key: StringSpan) raises:
        """Writes one string map key and prepares for its value.

        Args:
            key: Decoded protobuf map key.

        Raises:
            Error: If no map field value is open.
        """
        if not self._in_map:
            raise Error("proto json: map writer state is empty")
        if not self._first_field:
            self._buf.append(UInt8(0x2C))
        self._first_field = False
        _append_quoted(self._buf, key)
        self._buf.append(UInt8(0x3A))

    def end_map(mut self) raises:
        """Ends a protobuf map object.

        Raises:
            Error: If no map field value is open.
        """
        if not self._in_map:
            raise Error("proto json: map writer state is empty")
        self._buf.append(UInt8(0x7D))
        self._first_field = self._map_parent_first
        self._in_map = False

    def begin_array(mut self) raises:
        """Starts a repeated field value.

        Raises:
            Error: If another repeated field value is still open.
        """
        if self._in_array or self._in_map:
            raise Error("proto json: nested arrays are not supported")
        self._buf.append(UInt8(0x5B))
        self._array_parent_first = self._first_field
        self._first_field = True
        self._in_array = True

    def array_item(mut self) raises:
        """Starts the next repeated field element.

        Raises:
            Error: If no repeated field value is open.
        """
        if not self._in_array:
            raise Error("proto json: array writer state is empty")
        if not self._first_field:
            self._buf.append(UInt8(0x2C))
        self._first_field = False

    def end_array(mut self) raises:
        """Ends a repeated field value.

        Raises:
            Error: If no repeated field value is open.
        """
        if not self._in_array:
            raise Error("proto json: array writer state is empty")
        self._buf.append(UInt8(0x5D))
        self._first_field = self._array_parent_first
        self._in_array = False

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

    def finite_float64_value(mut self, value: Float64) raises:
        """Writes a finite JSON number.

        `google.protobuf.Value` uses ordinary JSON numbers and cannot encode
        the quoted non-finite spellings allowed for protobuf double fields.

        Args:
            value: Value to write.

        Raises:
            Error: If the value is NaN or infinity.
        """
        if _float64_is_nan(value) or _float64_is_inf(value):
            raise Error("proto json: Value number must be finite")
        self._buf.extend(String(value).as_bytes())

    def null_value(mut self):
        """Writes the JSON null literal."""
        _append_ascii(self._buf, "null")

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

    def timestamp_value(
        mut self, seconds: Int64, nanos: Int32
    ) raises:
        """Writes a protobuf Timestamp as canonical RFC 3339 text.

        Args:
            seconds: Whole seconds since the Unix epoch.
            nanos: Nanoseconds after `seconds`.

        Raises:
            Error: If either value is outside the Timestamp range.
        """
        if seconds < -62135596800 or seconds > 253402300799:
            raise Error("proto json: timestamp seconds out of range")
        if nanos < 0 or nanos > 999999999:
            raise Error("proto json: timestamp nanos out of range")

        var days = seconds // 86400
        var day_seconds = seconds - days * 86400
        if day_seconds < 0:
            days -= 1
            day_seconds += 86400
        var civil = _civil_from_epoch_days(days)
        var hour = Int(day_seconds // 3600)
        var minute = Int((day_seconds % 3600) // 60)
        var second = Int(day_seconds % 60)

        self._buf.append(UInt8(0x22))
        _append_padded_decimal(self._buf, civil[0], 4)
        self._buf.append(UInt8(0x2D))
        _append_padded_decimal(self._buf, civil[1], 2)
        self._buf.append(UInt8(0x2D))
        _append_padded_decimal(self._buf, civil[2], 2)
        self._buf.append(UInt8(0x54))
        _append_padded_decimal(self._buf, hour, 2)
        self._buf.append(UInt8(0x3A))
        _append_padded_decimal(self._buf, minute, 2)
        self._buf.append(UInt8(0x3A))
        _append_padded_decimal(self._buf, second, 2)
        if nanos != 0:
            self._buf.append(UInt8(0x2E))
            if nanos % 1000000 == 0:
                _append_padded_decimal(
                    self._buf, Int(nanos // 1000000), 3
                )
            elif nanos % 1000 == 0:
                _append_padded_decimal(self._buf, Int(nanos // 1000), 6)
            else:
                _append_padded_decimal(self._buf, Int(nanos), 9)
        _append_ascii(self._buf, 'Z"')

    def duration_value(
        mut self, seconds: Int64, nanos: Int32
    ) raises:
        """Writes a protobuf Duration using its canonical JSON text.

        Args:
            seconds: Whole seconds in the duration.
            nanos: The signed fractional second.

        Raises:
            Error: If the values are out of range or have different signs.
        """
        if seconds < -315576000000 or seconds > 315576000000:
            raise Error("proto json: duration seconds out of range")
        if nanos < -999999999 or nanos > 999999999:
            raise Error("proto json: duration nanos out of range")
        if (seconds < 0 and nanos > 0) or (seconds > 0 and nanos < 0):
            raise Error("proto json: duration sign mismatch")

        var negative = seconds < 0 or nanos < 0
        var second_magnitude = -seconds if seconds < 0 else seconds
        var nano_magnitude = -Int(nanos) if nanos < 0 else Int(nanos)
        self._buf.append(UInt8(0x22))
        if negative:
            self._buf.append(UInt8(0x2D))
        self._buf.extend(String(second_magnitude).as_bytes())
        if nano_magnitude != 0:
            self._buf.append(UInt8(0x2E))
            if nano_magnitude % 1000000 == 0:
                _append_padded_decimal(
                    self._buf, nano_magnitude // 1000000, 3
                )
            elif nano_magnitude % 1000 == 0:
                _append_padded_decimal(self._buf, nano_magnitude // 1000, 6)
            else:
                _append_padded_decimal(self._buf, nano_magnitude, 9)
        _append_ascii(self._buf, 's"')

    def field_mask_value(mut self, paths: List[String]) raises:
        """Writes FieldMask paths as one comma-separated JSON string.

        Args:
            paths: Snake-case protobuf paths.

        Raises:
            Error: If a path cannot round-trip through lowerCamelCase.
        """
        var converted = List[Byte]()
        for path_index in range(len(paths)):
            if path_index != 0:
                converted.append(UInt8(0x2C))
            var path = paths[path_index].as_bytes()
            var pos = 0
            while pos < len(path):
                var b = path[pos]
                if b >= 0x41 and b <= 0x5A:
                    raise Error(
                        "proto json: field mask path has uppercase letter"
                    )
                if b == 0x5F:
                    pos += 1
                    if (
                        pos >= len(path)
                        or path[pos] < 0x61
                        or path[pos] > 0x7A
                    ):
                        raise Error("proto json: invalid field mask underscore")
                    converted.append(path[pos] - UInt8(0x20))
                else:
                    converted.append(b)
                pos += 1
        self.string_value(String(from_utf8=converted))

    def message_value[M: ProtoJsonMessage](mut self, value: M) raises:
        """Writes one nested message object.

        Parameters:
            M: A message type with a complete proto3 JSON mapping.

        Args:
            value: Nested message to write.

        Raises:
            Error: If the nested message cannot be written as valid JSON.
        """
        var nested = ProtoJsonWriter(self.options)
        value.encode_json_to(nested)
        var text = nested.take()
        self._buf.extend(text.as_bytes())

    def raw_json_value(mut self, text: StringSpan) raises:
        """Appends one complete, validated JSON value.

        Args:
            text: JSON value to append.

        Raises:
            Error: If the text is malformed or has trailing content.
        """
        var validator = ProtoJsonReader(text)
        validator._skip_value(0)
        validator.finish()
        self._buf.extend(text.as_bytes())

    def any_value(
        mut self, type_url: StringSpan, value: List[Byte]
    ) raises:
        """Writes one `google.protobuf.Any` JSON object.

        Args:
            type_url: URL naming the embedded message type.
            value: Serialized embedded message bytes.

        Raises:
            Error: If the URL, resolver, bytes, or resolved JSON is invalid.
        """
        if type_url.byte_length() == 0 and len(value) == 0:
            self.begin_object()
            self.end_object()
            return
        _ = any_type_name(type_url)
        if not self.options.type_resolver.print_any:
            raise Error("proto json: Any print resolver is required")
        var payload = self.options.type_resolver.print_any.value()(
            String(type_url),
            value.copy(),
            self.options.preserve_proto_field_names,
            self.options.always_print_fields_with_no_presence,
        )
        var nested = ProtoJsonWriter(self.options)
        nested.begin_object()
        nested.field("@type", "@type")
        nested.string_value(type_url)
        if payload.uses_value_field:
            nested.field("value", "value")
            nested.raw_json_value(payload.json)
        else:
            var embedded = ProtoJsonReader(payload.json)
            embedded.begin_object()
            while True:
                var field = embedded.next_field()
                if not field:
                    break
                var name = field.value()
                var proto_name = name.copy()
                nested.field(name, proto_name)
                nested.raw_json_value(embedded.raw_json_value())
            embedded.finish()
        nested.end_object()
        self._buf.extend(nested.take().as_bytes())

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
    var _array_parent_first: Bool
    var _in_array: Bool
    var _array_depth_charged: Bool
    var _map_parent_first: Bool
    var _in_map: Bool
    var _root_depth_charged: Bool

    def __init__(
        out self,
        text: StringSpan,
        options: JsonParseOptions = JsonParseOptions(),
        root_depth_charged: Bool = False,
    ):
        """Creates a reader over one complete JSON value.

        Args:
            text: JSON text to parse.
            options: Active proto3 JSON parse options.
            root_depth_charged: Whether an enclosing reader already counted
                this value's root container against the depth limit.
        """
        self.options = options.copy()
        self._data = List[Byte]()
        self._data.extend(text.as_bytes())
        self._pos = 0
        self._first_field = True
        self._array_parent_first = True
        self._in_array = False
        self._array_depth_charged = False
        self._map_parent_first = True
        self._in_map = False
        self._root_depth_charged = root_depth_charged

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

    def begin_map(mut self) raises:
        """Starts reading a protobuf map object.

        Raises:
            Error: If the next value is not an object, another container is
                open, or the object exceeds the depth limit.
        """
        if self._in_map or self._in_array:
            raise Error("proto json: nested map reader state")
        if self.options.max_depth < 2:
            raise Error("proto json: maximum nesting depth exceeded")
        self._consume(UInt8(0x7B))
        self._map_parent_first = self._first_field
        self._first_field = True
        self._in_map = True

    def next_map_key(mut self) raises -> Optional[String]:
        """Returns the next decoded map key, or none at the object end.

        Returns:
            The decoded map key, or none after the closing brace.

        Raises:
            Error: If no map is open or the object syntax is malformed.
        """
        if not self._in_map:
            raise Error("proto json: map reader state is empty")
        self._skip_ws()
        if self._first_field:
            self._first_field = False
            if self._pos < len(self._data) and self._data[self._pos] == 0x7D:
                self._pos += 1
                self._first_field = self._map_parent_first
                self._in_map = False
                return None
        else:
            if self._pos < len(self._data) and self._data[self._pos] == 0x7D:
                self._pos += 1
                self._first_field = self._map_parent_first
                self._in_map = False
                return None
            self._consume(UInt8(0x2C))
            self._skip_ws()
            if self._pos < len(self._data) and self._data[self._pos] == 0x7D:
                raise Error("proto json: trailing comma")
        var key = self.string_value()
        self._consume(UInt8(0x3A))
        return key^

    def begin_array(mut self) raises:
        """Starts reading a repeated field value.

        Raises:
            Error: If the next value is not an array or exceeds the depth
                limit.
        """
        if self._in_array or self._in_map:
            raise Error("proto json: nested arrays are not supported")
        if self.options.max_depth < 2:
            raise Error("proto json: maximum nesting depth exceeded")
        self._consume(UInt8(0x5B))
        self._array_parent_first = self._first_field
        self._first_field = True
        self._in_array = True
        self._array_depth_charged = False

    def next_array_item(mut self) raises -> Bool:
        """Advances to the next repeated field element.

        Returns:
            True when an element follows, or false after the closing bracket.

        Raises:
            Error: If the array syntax is invalid.
        """
        if not self._in_array:
            raise Error("proto json: array reader state is empty")
        self._skip_ws()
        if self._first_field:
            self._first_field = False
            if self._pos < len(self._data) and self._data[self._pos] == 0x5D:
                self._pos += 1
                self._first_field = self._array_parent_first
                self._in_array = False
                return False
            return True
        if self._pos < len(self._data) and self._data[self._pos] == 0x5D:
            self._pos += 1
            self._first_field = self._array_parent_first
            self._in_array = False
            return False
        self._consume(UInt8(0x2C))
        self._skip_ws()
        if self._pos < len(self._data) and self._data[self._pos] == 0x5D:
            raise Error("proto json: trailing comma")
        return True

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

    def next_value_kind(mut self) raises -> UInt8:
        """Reports the next JSON value kind without consuming it.

        Returns:
            Zero for null, one for string, two for number, three for boolean,
            four for object, or five for array.

        Raises:
            Error: If the next token cannot start a JSON value.
        """
        self._skip_ws()
        if self._pos >= len(self._data):
            raise Error("proto json: missing value")
        var b = self._data[self._pos]
        if b == 0x6E:
            return UInt8(0)
        if b == 0x22:
            return UInt8(1)
        if b == 0x2D or (b >= 0x30 and b <= 0x39):
            return UInt8(2)
        if b == 0x74 or b == 0x66:
            return UInt8(3)
        if b == 0x7B:
            return UInt8(4)
        if b == 0x5B:
            return UInt8(5)
        raise Error("proto json: invalid value")

    def begin_value_array(mut self) raises:
        """Starts an array that is itself the current protobuf JSON value.

        Raises:
            Error: If the input is not an array or exceeds the depth limit.
        """
        if self._in_array or self._in_map:
            raise Error("proto json: nested arrays are not supported")
        if not self._root_depth_charged and self.options.max_depth < 1:
            raise Error("proto json: maximum nesting depth exceeded")
        self._consume(UInt8(0x5B))
        self._array_parent_first = self._first_field
        self._first_field = True
        self._in_array = True
        self._array_depth_charged = True

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
            if (
                value == 0.0
                and token.byte_length() != 0
                and token.as_bytes()[0] == 0x2D
            ):
                return Float64(from_bits=UInt64(0x8000000000000000))
            return value
        var token = self._number_token()
        var value = Float64(token)
        if _float64_is_inf(value):
            raise Error("proto json: floating-point value out of range")
        if (
            value == 0.0
            and token.byte_length() != 0
            and token.as_bytes()[0] == 0x2D
        ):
            return Float64(from_bits=UInt64(0x8000000000000000))
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

    def timestamp_value(mut self) raises -> Tuple[Int64, Int32]:
        """Reads a protobuf Timestamp from RFC 3339 text.

        Returns:
            Whole epoch seconds and nanoseconds.

        Raises:
            Error: If the timestamp is malformed or outside its range.
        """
        var text = self.string_value()
        var data = text.as_bytes()
        if len(data) < 20:
            raise Error("proto json: invalid timestamp")
        if (
            data[4] != 0x2D
            or data[7] != 0x2D
            or data[10] != 0x54
            or data[13] != 0x3A
            or data[16] != 0x3A
        ):
            raise Error("proto json: invalid timestamp layout")

        var year = _decimal_at(data, 0, 4)
        var month = _decimal_at(data, 5, 2)
        var day = _decimal_at(data, 8, 2)
        var hour = _decimal_at(data, 11, 2)
        var minute = _decimal_at(data, 14, 2)
        var second = _decimal_at(data, 17, 2)
        if year < 1 or year > 9999 or month < 1 or month > 12:
            raise Error("proto json: timestamp date out of range")
        if day < 1 or day > _days_in_month(year, month):
            raise Error("proto json: timestamp day out of range")
        if hour > 23 or minute > 59 or second > 59:
            raise Error("proto json: timestamp time out of range")

        var pos = 19
        var nanos = 0
        if data[pos] == 0x2E:
            pos += 1
            var digits = 0
            while (
                pos < len(data)
                and data[pos] >= 0x30
                and data[pos] <= 0x39
            ):
                if digits == 9:
                    raise Error("proto json: too many timestamp digits")
                nanos = nanos * 10 + Int(data[pos] - 0x30)
                digits += 1
                pos += 1
            if digits == 0:
                raise Error("proto json: empty timestamp fraction")
            for _ in range(9 - digits):
                nanos *= 10
        if pos >= len(data):
            raise Error("proto json: missing timestamp offset")

        var offset_seconds = 0
        if data[pos] == 0x5A:
            if pos + 1 != len(data):
                raise Error("proto json: trailing timestamp data")
        elif data[pos] == 0x2B or data[pos] == 0x2D:
            var positive = data[pos] == 0x2B
            if pos + 6 != len(data) or data[pos + 3] != 0x3A:
                raise Error("proto json: invalid timestamp offset")
            var offset_hour = _decimal_at(data, pos + 1, 2)
            var offset_minute = _decimal_at(data, pos + 4, 2)
            if offset_hour > 23 or offset_minute > 59:
                raise Error("proto json: timestamp offset out of range")
            offset_seconds = (offset_hour * 60 + offset_minute) * 60
            if positive:
                offset_seconds = -offset_seconds
        else:
            raise Error("proto json: invalid timestamp offset")

        var seconds = (
            _epoch_days_from_civil(year, month, day) * 86400
            + Int64(hour * 3600 + minute * 60 + second + offset_seconds)
        )
        if seconds < -62135596800 or seconds > 253402300799:
            raise Error("proto json: timestamp seconds out of range")
        return seconds, Int32(nanos)

    def duration_value(mut self) raises -> Tuple[Int64, Int32]:
        """Reads a protobuf Duration from its signed decimal JSON text.

        Returns:
            Whole seconds and signed nanoseconds.

        Raises:
            Error: If the duration is malformed or outside its range.
        """
        var text = self.string_value()
        var data = text.as_bytes()
        if len(data) < 2 or data[len(data) - 1] != 0x73:
            raise Error("proto json: invalid duration suffix")

        var pos = 0
        var negative = False
        if data[pos] == 0x2D:
            negative = True
            pos += 1
        if pos >= len(data) - 1:
            raise Error("proto json: missing duration seconds")

        var seconds = Int64(0)
        var second_digits = 0
        while (
            pos < len(data) - 1
            and data[pos] >= 0x30
            and data[pos] <= 0x39
        ):
            var digit = Int64(data[pos] - 0x30)
            if seconds > (Int64(315576000000) - digit) // 10:
                raise Error("proto json: duration seconds out of range")
            seconds = seconds * 10 + digit
            second_digits += 1
            pos += 1
        if second_digits == 0:
            raise Error("proto json: missing duration seconds")

        var nanos = 0
        if pos < len(data) - 1 and data[pos] == 0x2E:
            pos += 1
            var digits = 0
            while (
                pos < len(data) - 1
                and data[pos] >= 0x30
                and data[pos] <= 0x39
            ):
                if digits == 9:
                    raise Error("proto json: too many duration digits")
                nanos = nanos * 10 + Int(data[pos] - 0x30)
                digits += 1
                pos += 1
            for _ in range(9 - digits):
                nanos *= 10
        if pos != len(data) - 1:
            raise Error("proto json: invalid duration")
        if negative:
            seconds = -seconds
            nanos = -nanos
        return seconds, Int32(nanos)

    def field_mask_value(mut self) raises -> List[String]:
        """Reads comma-separated lowerCamelCase FieldMask paths.

        Returns:
            Snake-case protobuf paths.

        Raises:
            Error: If a path contains an underscore.
        """
        var text = self.string_value()
        if text.byte_length() == 0:
            return List[String]()

        var paths = List[String]()
        for path in text.split(","):
            var converted = List[Byte]()
            for b in path.as_bytes():
                if b == 0x5F:
                    raise Error("proto json: field mask path has underscore")
                if b >= 0x41 and b <= 0x5A:
                    converted.append(UInt8(0x5F))
                    converted.append(b + UInt8(0x20))
                else:
                    converted.append(b)
            paths.append(String(from_utf8=converted))
        return paths^

    def message_value[M: ProtoJsonMessage](mut self) raises -> M:
        """Reads one nested message value.

        Parameters:
            M: A message type with a complete proto3 JSON mapping.

        Returns:
            The decoded nested message.

        Raises:
            Error: If the next value is not valid for the message.
        """
        self._skip_ws()
        if self._pos >= len(self._data):
            raise Error("proto json: missing message value")
        var start = self._pos
        var depth = 1
        if self._in_map or (self._in_array and not self._array_depth_charged):
            depth = 2
        self._skip_value(depth)
        var encoded = List[Byte]()
        encoded.extend(Span(self._data)[start : self._pos])
        var text = String(from_utf8=encoded)
        var nested_options = self.options.copy()
        nested_options.max_depth -= depth
        var nested = ProtoJsonReader(
            text, nested_options, root_depth_charged=True
        )
        var message = M()
        message.merge_json_from(nested)
        nested.finish()
        return message^

    def same_value_message[M: ProtoJsonMessage](mut self) raises -> M:
        """Reads a message that shares the current JSON value.

        `google.protobuf.Value` delegates objects and arrays to Struct and
        ListValue without adding another JSON nesting level.

        Parameters:
            M: The message type that owns the current JSON representation.

        Returns:
            The decoded message.

        Raises:
            Error: If the current value is not valid for the message.
        """
        self._skip_ws()
        if self._pos >= len(self._data):
            raise Error("proto json: missing message value")
        var start = self._pos
        var depth = 0
        self._skip_value(depth)
        var encoded = List[Byte]()
        encoded.extend(Span(self._data)[start : self._pos])
        var text = String(from_utf8=encoded)
        var nested_options = self.options.copy()
        nested_options.max_depth -= depth
        var nested = ProtoJsonReader(
            text, nested_options, root_depth_charged=True
        )
        var message = M()
        message.merge_json_from(nested)
        nested.finish()
        return message^

    def raw_json_value(mut self) raises -> String:
        """Consumes and returns one complete JSON value.

        Returns:
            The original JSON text for the value.

        Raises:
            Error: If the value is malformed or exceeds the depth limit.
        """
        self._skip_ws()
        var start = self._pos
        self._skip_value(0)
        var encoded = List[Byte]()
        encoded.extend(Span(self._data)[start : self._pos])
        return String(from_utf8=encoded)

    def any_value(mut self) raises -> Tuple[String, List[Byte]]:
        """Reads one `google.protobuf.Any` JSON object.

        Returns:
            The type URL and serialized embedded message bytes.

        Raises:
            Error: If the object, URL, resolver, or embedded message is
                invalid.
        """
        var encoded = self.raw_json_value()
        var envelope = ProtoJsonReader(
            encoded, self.options, root_depth_charged=True
        )
        envelope.begin_object()
        var type_url = String()
        var saw_type = False
        var saw_field = False
        while True:
            var field = envelope.next_field()
            if not field:
                break
            saw_field = True
            if field.value() == "@type":
                if saw_type:
                    raise Error("proto json: duplicate Any @type")
                saw_type = True
                type_url = envelope.string_value()
            else:
                _ = envelope.raw_json_value()
        envelope.finish()
        if not saw_field:
            return String(), List[Byte]()
        if not saw_type:
            raise Error("proto json: Any @type is missing")
        _ = any_type_name(type_url)
        if not self.options.type_resolver.parse_any:
            raise Error("proto json: Any parse resolver is required")
        var value = self.options.type_resolver.parse_any.value()(
            type_url,
            encoded,
            self.options.ignore_unknown_fields,
            self.options.max_depth,
        )
        return type_url^, value^

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


def any_type_name(type_url: StringSpan) raises -> String:
    """Returns the message name after the final slash in an Any type URL.

    Args:
        type_url: Type URL to validate.

    Returns:
        The fully qualified protobuf message name.

    Raises:
        Error: If the URL has an empty prefix or message name.
    """
    var data = type_url.as_bytes()
    var slash = -1
    for index in range(len(data)):
        if data[index] == 0x2F:
            slash = index
    if slash <= 0 or slash + 1 >= len(data):
        raise Error("proto json: invalid Any type URL")
    var name = List[Byte]()
    name.extend(data[slash + 1 :])
    return String(from_utf8=name)


def extract_any_json_payload(
    text: StringSpan,
    type_url: StringSpan,
    *,
    uses_value_field: Bool,
    ignore_unknown_fields: Bool = False,
    max_depth: Int = 100,
) raises -> String:
    """Extracts embedded JSON from one validated Any object.

    Args:
        text: Complete Any JSON object.
        type_url: Expected type URL.
        uses_value_field: Whether to require the well-known `value` form.
        ignore_unknown_fields: Preserved for the embedded parse options.
        max_depth: Remaining JSON depth budget.

    Returns:
        JSON for the embedded message.

    Raises:
        Error: If the envelope is malformed or does not match the requested
            Any form.
    """
    _ = ignore_unknown_fields
    var options = JsonParseOptions(max_depth=max_depth)
    var reader = ProtoJsonReader(text, options)
    var ordinary = ProtoJsonWriter()
    ordinary.begin_object()
    var payload = String()
    var saw_type = False
    var saw_value = False
    reader.begin_object()
    while True:
        var field = reader.next_field()
        if not field:
            break
        var name = field.value()
        if name == "@type":
            if saw_type:
                raise Error("proto json: duplicate Any @type")
            saw_type = True
            if reader.string_value() != type_url:
                raise Error("proto json: Any type URL changed during resolve")
        elif uses_value_field:
            if name != "value" or saw_value:
                raise Error("proto json: invalid Any well-known value form")
            saw_value = True
            payload = reader.raw_json_value()
        else:
            var proto_name = name.copy()
            ordinary.field(name, proto_name)
            ordinary.raw_json_value(reader.raw_json_value())
    reader.finish()
    if not saw_type:
        raise Error("proto json: Any @type is missing")
    if uses_value_field:
        if not saw_value:
            raise Error("proto json: Any value is missing")
        return payload^
    ordinary.end_object()
    return ordinary.take()


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


def print_any_json_payload[
    M: ProtoJsonMessage
](
    value: List[Byte],
    options: JsonPrintOptions,
    *,
    uses_value_field: Bool = False,
) raises -> AnyJsonPayload:
    """Decodes and prints one statically resolved Any payload.

    Parameters:
        M: The embedded message type selected by a generated resolver.

    Args:
        value: Serialized embedded message bytes.
        options: Print options inherited from the enclosing message.
        uses_value_field: Whether the Any envelope uses the well-known
            `value` form.

    Returns:
        The embedded JSON and its envelope form.

    Raises:
        Error: If the wire value or embedded JSON is invalid.
    """
    var message = decode[M](Span(value))
    return AnyJsonPayload(
        encode_json(message, options=options),
        uses_value_field=uses_value_field,
    )


def parse_any_json_payload[
    M: ProtoJsonMessage
](
    text: String,
    type_url: String,
    type_resolver: ProtoJsonTypeResolver,
    ignore_unknown_fields: Bool,
    max_depth: Int,
    *,
    uses_value_field: Bool = False,
) raises -> List[Byte]:
    """Parses one statically resolved Any payload.

    Parameters:
        M: The embedded message type selected by a generated resolver.

    Args:
        text: Complete Any JSON object.
        type_url: Type URL already selected by the resolver.
        type_resolver: Resolver used by nested Any values.
        ignore_unknown_fields: Whether embedded messages ignore unknown fields.
        max_depth: Remaining depth budget for the Any object.
        uses_value_field: Whether the Any envelope uses the well-known
            `value` form.

    Returns:
        Serialized embedded message bytes.

    Raises:
        Error: If the envelope or embedded message is invalid.
    """
    var payload = extract_any_json_payload(
        text,
        type_url,
        uses_value_field=uses_value_field,
        ignore_unknown_fields=ignore_unknown_fields,
        max_depth=max_depth,
    )
    var payload_depth = max_depth
    if uses_value_field:
        payload_depth -= 1
    var options = JsonParseOptions(
        ignore_unknown_fields=ignore_unknown_fields,
        max_depth=payload_depth,
        type_resolver=type_resolver,
    )
    return encode(decode_json[M](payload, options=options))
