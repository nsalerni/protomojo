# Hand-written messages mirroring test/proto/vectors.proto.
#
# These are the reference for what tools/protoc-gen-mojo emits: every
# construct here (scalars, submessages, repeated/packed, maps, oneofs)
# is a codegen template.

from proto import (
    WIRE_LEN,
    WIRE_VARINT,
    ProtoMessage,
    WireReader,
    WireWriter,
)


struct Scalars(Copyable, Defaultable, Movable, ProtoMessage):
    var f_int32: Int32  # 1
    var f_int64: Int64  # 2
    var f_uint32: UInt32  # 3
    var f_uint64: UInt64  # 4
    var f_sint32: Int32  # 5
    var f_sint64: Int64  # 6
    var f_bool: Bool  # 7
    var f_fixed32: UInt32  # 8
    var f_fixed64: UInt64  # 9
    var f_sfixed32: Int32  # 10
    var f_sfixed64: Int64  # 11
    var f_float: Float32  # 12
    var f_double: Float64  # 13
    var f_string: String  # 14
    var f_bytes: List[Byte]  # 15
    var f_big_field: Int32  # 1000
    var _unknown: List[Byte]

    def __init__(out self):
        self.f_int32 = 0
        self.f_int64 = 0
        self.f_uint32 = 0
        self.f_uint64 = 0
        self.f_sint32 = 0
        self.f_sint64 = 0
        self.f_bool = False
        self.f_fixed32 = 0
        self.f_fixed64 = 0
        self.f_sfixed32 = 0
        self.f_sfixed64 = 0
        self.f_float = 0.0
        self.f_double = 0.0
        self.f_string = String()
        self.f_bytes = List[Byte]()
        self.f_big_field = 0
        self._unknown = List[Byte]()

    def encode_to(self, mut writer: WireWriter):
        if self.f_int32 != 0:
            writer.int32(1, self.f_int32)
        if self.f_int64 != 0:
            writer.int64(2, self.f_int64)
        if self.f_uint32 != 0:
            writer.uint32(3, self.f_uint32)
        if self.f_uint64 != 0:
            writer.uint64(4, self.f_uint64)
        if self.f_sint32 != 0:
            writer.sint32(5, self.f_sint32)
        if self.f_sint64 != 0:
            writer.sint64(6, self.f_sint64)
        if self.f_bool:
            writer.bool_field(7, self.f_bool)
        if self.f_fixed32 != 0:
            writer.fixed32_field(8, self.f_fixed32)
        if self.f_fixed64 != 0:
            writer.fixed64_field(9, self.f_fixed64)
        if self.f_sfixed32 != 0:
            writer.sfixed32_field(10, self.f_sfixed32)
        if self.f_sfixed64 != 0:
            writer.sfixed64_field(11, self.f_sfixed64)
        if self.f_float != 0.0:
            writer.float_field(12, self.f_float)
        if self.f_double != 0.0:
            writer.double_field(13, self.f_double)
        if self.f_string.byte_length() != 0:
            writer.string_field(14, self.f_string)
        if len(self.f_bytes) != 0:
            writer.bytes_field(15, Span(self.f_bytes))
        if self.f_big_field != 0:
            writer.int32(1000, self.f_big_field)
        writer.buf.extend(Span(self._unknown))

    def merge_from(mut self, mut reader: WireReader) raises:
        while not reader.done():
            var tag = reader.read_tag()
            var field = tag[0]
            var wire_type = tag[1]
            if field == 1:
                self.f_int32 = reader.int32_value()
            elif field == 2:
                self.f_int64 = reader.int64_value()
            elif field == 3:
                self.f_uint32 = reader.uint32_value()
            elif field == 4:
                self.f_uint64 = reader.varint()
            elif field == 5:
                self.f_sint32 = reader.sint32_value()
            elif field == 6:
                self.f_sint64 = reader.sint64_value()
            elif field == 7:
                self.f_bool = reader.bool_value()
            elif field == 8:
                self.f_fixed32 = reader.fixed32()
            elif field == 9:
                self.f_fixed64 = reader.fixed64()
            elif field == 10:
                self.f_sfixed32 = reader.sfixed32_value()
            elif field == 11:
                self.f_sfixed64 = reader.sfixed64_value()
            elif field == 12:
                self.f_float = reader.float_value()
            elif field == 13:
                self.f_double = reader.double_value()
            elif field == 14:
                self.f_string = reader.string_value()
            elif field == 15:
                self.f_bytes = reader.bytes_value()
            elif field == 1000:
                self.f_big_field = reader.int32_value()
            else:
                reader.capture_field(field, wire_type, self._unknown)


struct Nested(Defaultable, Movable, ProtoMessage):
    var inner: Optional[Scalars]  # 1
    var packed_ints: List[Int32]  # 2, packed
    var names: List[String]  # 3
    var inners: List[Scalars]  # 4
    var counts: Dict[String, Int32]  # 5, map<string, int32>
    # oneof choice: 0 = unset, 6 = as_text, 7 = as_num
    var choice_case: Int
    var as_text: String  # 6
    var as_num: Int64  # 7
    var _unknown: List[Byte]

    def __init__(out self):
        self.inner = None
        self.packed_ints = List[Int32]()
        self.names = List[String]()
        self.inners = List[Scalars]()
        self.counts = Dict[String, Int32]()
        self.choice_case = 0
        self.as_text = String()
        self.as_num = 0
        self._unknown = List[Byte]()

    def encode_to(self, mut writer: WireWriter):
        if self.inner:
            var sub = WireWriter()
            self.inner.value().encode_to(sub)
            writer.len_prefixed(1, Span(sub.buf))
        if len(self.packed_ints) != 0:
            var sub = WireWriter()
            for v in self.packed_ints:
                sub.varint(UInt64(Int64(v)))
            writer.len_prefixed(2, Span(sub.buf))
        for name in self.names:
            writer.string_field(3, name)
        for m in self.inners:
            var sub = WireWriter()
            m.encode_to(sub)
            writer.len_prefixed(4, Span(sub.buf))
        for entry in self.counts.items():
            var sub = WireWriter()
            sub.string_field(1, entry.key)
            if entry.value != 0:
                sub.int32(2, entry.value)
            writer.len_prefixed(5, Span(sub.buf))
        if self.choice_case == 6:
            writer.string_field(6, self.as_text)
        elif self.choice_case == 7:
            writer.int64(7, self.as_num)
        writer.buf.extend(Span(self._unknown))

    def merge_from(mut self, mut reader: WireReader) raises:
        while not reader.done():
            var tag = reader.read_tag()
            var field = tag[0]
            var wire_type = tag[1]
            if field == 1:
                # Duplicate singular submessages merge field-level (spec
                # §"Last One Wins" applies per field, not per message).
                var sub = reader.sub_reader()
                var m: Scalars
                if self.inner:
                    m = self.inner.take()
                else:
                    m = Scalars()
                m.merge_from(sub)
                self.inner = m^
            elif field == 2:
                if wire_type == WIRE_LEN:
                    # packed
                    var sub = reader.sub_reader()
                    while not sub.done():
                        self.packed_ints.append(sub.int32_value())
                else:
                    # parsers must also accept unpacked
                    self.packed_ints.append(reader.int32_value())
            elif field == 3:
                self.names.append(reader.string_value())
            elif field == 4:
                var sub = reader.sub_reader()
                var m = Scalars()
                m.merge_from(sub)
                self.inners.append(m^)
            elif field == 5:
                var sub = reader.sub_reader()
                var key = String()
                var value: Int32 = 0
                while not sub.done():
                    var etag = sub.read_tag()
                    if etag[0] == 1:
                        key = sub.string_value()
                    elif etag[0] == 2:
                        value = sub.int32_value()
                    else:
                        sub.skip(etag[1])
                self.counts[key^] = value
            elif field == 6:
                self.choice_case = 6
                self.as_text = reader.string_value()
                self.as_num = 0
            elif field == 7:
                self.choice_case = 7
                self.as_num = reader.int64_value()
                self.as_text = String()
            else:
                reader.capture_field(field, wire_type, self._unknown)


struct EchoRequest(Copyable, Defaultable, Movable, ProtoMessage):
    var message: String  # 1
    var _unknown: List[Byte]

    def __init__(out self):
        self.message = String()
        self._unknown = List[Byte]()

    def __init__(out self, var message: String):
        self.message = message^
        self._unknown = List[Byte]()

    def encode_to(self, mut writer: WireWriter):
        if self.message.byte_length() != 0:
            writer.string_field(1, self.message)
        writer.buf.extend(Span(self._unknown))

    def merge_from(mut self, mut reader: WireReader) raises:
        while not reader.done():
            var tag = reader.read_tag()
            if tag[0] == 1:
                self.message = reader.string_value()
            else:
                reader.capture_field(tag[0], tag[1], self._unknown)


struct EchoResponse(Copyable, Defaultable, Movable, ProtoMessage):
    var message: String  # 1
    var _unknown: List[Byte]

    def __init__(out self):
        self.message = String()
        self._unknown = List[Byte]()

    def __init__(out self, var message: String):
        self.message = message^
        self._unknown = List[Byte]()

    def encode_to(self, mut writer: WireWriter):
        if self.message.byte_length() != 0:
            writer.string_field(1, self.message)
        writer.buf.extend(Span(self._unknown))

    def merge_from(mut self, mut reader: WireReader) raises:
        while not reader.done():
            var tag = reader.read_tag()
            if tag[0] == 1:
                self.message = reader.string_value()
            else:
                reader.capture_field(tag[0], tag[1], self._unknown)
