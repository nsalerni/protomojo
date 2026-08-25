# Compliance tool for generated proto3 JSON messages.
#
# Usage: proto_json_codec <mode> <infile> <outfile>
#
# Parse modes accept one JSON object per line and write protobuf bytes as hex.
# Print modes accept one hex protobuf message per line and write one JSON object.

from std.sys import argv

from proto import JsonParseOptions, decode, decode_json, encode, encode_json
from empty_pb import Empty
from duration_pb import Duration
from field_mask_pb import FieldMask
from struct_pb import ListValue, Struct, Value
from timestamp_pb import Timestamp
from wrappers_pb import Int32Value
from testutil import from_hex, to_hex
from vectors_pb import (
    EnumValue,
    JsonEmptyParent,
    JsonDuration,
    JsonDescriptorMessages,
    JsonFieldMask,
    JsonKeyMaps,
    JsonMessageMaps,
    JsonOneof,
    JsonOptional,
    JsonParent,
    JsonRepeated,
    JsonRepeatedMessages,
    JsonStringMaps,
    JsonStructValues,
    JsonTimestamp,
    JsonWrappers,
    Scalars,
    Tree,
)


def run(mode: StringSpan, text: String) raises -> String:
    var out = String()
    for line in text.split("\n"):
        if line.byte_length() == 0:
            continue
        try:
            if mode == "parse":
                var message = decode_json[Scalars](line)
                out += to_hex(encode(message))
            elif mode == "print":
                var raw = from_hex(line.strip())
                var message = decode[Scalars](Span(raw))
                out += encode_json(message)
            elif mode == "parse-enum":
                var message = decode_json[EnumValue](line)
                out += to_hex(encode(message))
            elif mode == "parse-enum-ignore-unknown":
                var options = JsonParseOptions(ignore_unknown_fields=True)
                var message = decode_json[EnumValue](line, options=options)
                out += to_hex(encode(message))
            elif mode == "print-enum":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[EnumValue](Span(raw))
                out += encode_json(message)
            elif mode == "parse-nested":
                var message = decode_json[JsonParent](line)
                out += to_hex(encode(message))
            elif mode == "print-nested":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonParent](Span(raw))
                out += encode_json(message)
            elif mode == "parse-repeated":
                var message = decode_json[JsonRepeated](line)
                out += to_hex(encode(message))
            elif mode == "parse-repeated-ignore-unknown":
                var options = JsonParseOptions(ignore_unknown_fields=True)
                var message = decode_json[JsonRepeated](line, options=options)
                out += to_hex(encode(message))
            elif mode == "print-repeated":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonRepeated](Span(raw))
                out += encode_json(message)
            elif mode == "parse-repeated-messages":
                var message = decode_json[JsonRepeatedMessages](line)
                out += to_hex(encode(message))
            elif mode == "parse-repeated-messages-ignore-unknown":
                var options = JsonParseOptions(ignore_unknown_fields=True)
                var message = decode_json[JsonRepeatedMessages](
                    line, options=options
                )
                out += to_hex(encode(message))
            elif mode == "print-repeated-messages":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonRepeatedMessages](Span(raw))
                out += encode_json(message)
            elif mode == "parse-string-maps":
                var message = decode_json[JsonStringMaps](line)
                out += to_hex(encode(message))
            elif mode == "parse-string-maps-ignore-unknown":
                var options = JsonParseOptions(ignore_unknown_fields=True)
                var message = decode_json[JsonStringMaps](line, options=options)
                out += to_hex(encode(message))
            elif mode == "print-string-maps":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonStringMaps](Span(raw))
                out += encode_json(message)
            elif mode == "parse-key-maps":
                var message = decode_json[JsonKeyMaps](line)
                out += to_hex(encode(message))
            elif mode == "print-key-maps":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonKeyMaps](Span(raw))
                out += encode_json(message)
            elif mode == "parse-message-maps":
                var message = decode_json[JsonMessageMaps](line)
                out += to_hex(encode(message))
            elif mode == "parse-message-maps-ignore-unknown":
                var options = JsonParseOptions(ignore_unknown_fields=True)
                var message = decode_json[JsonMessageMaps](line, options=options)
                out += to_hex(encode(message))
            elif mode == "print-message-maps":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonMessageMaps](Span(raw))
                out += encode_json(message)
            elif mode == "parse-oneof":
                var message = decode_json[JsonOneof](line)
                out += to_hex(encode(message))
            elif mode == "parse-oneof-ignore-unknown":
                var options = JsonParseOptions(ignore_unknown_fields=True)
                var message = decode_json[JsonOneof](line, options=options)
                out += to_hex(encode(message))
            elif mode == "print-oneof":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonOneof](Span(raw))
                out += encode_json(message)
            elif mode == "parse-optional":
                var message = decode_json[JsonOptional](line)
                out += to_hex(encode(message))
            elif mode == "parse-optional-ignore-unknown":
                var options = JsonParseOptions(ignore_unknown_fields=True)
                var message = decode_json[JsonOptional](
                    line, options=options
                )
                out += to_hex(encode(message))
            elif mode == "print-optional":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonOptional](Span(raw))
                out += encode_json(message)
            elif mode == "parse-empty":
                var message = decode_json[Empty](line)
                out += to_hex(encode(message))
            elif mode == "parse-empty-ignore-unknown":
                var options = JsonParseOptions(ignore_unknown_fields=True)
                var message = decode_json[Empty](line, options=options)
                out += to_hex(encode(message))
            elif mode == "print-empty":
                var message = Empty()
                out += encode_json(message)
            elif mode == "parse-empty-parent":
                var message = decode_json[JsonEmptyParent](line)
                out += to_hex(encode(message))
            elif mode == "print-empty-parent":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonEmptyParent](Span(raw))
                out += encode_json(message)
            elif mode == "parse-wrapper-int32":
                var message = decode_json[Int32Value](line)
                out += to_hex(encode(message))
            elif mode == "print-wrapper-int32":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[Int32Value](Span(raw))
                out += encode_json(message)
            elif mode == "parse-wrappers":
                var message = decode_json[JsonWrappers](line)
                out += to_hex(encode(message))
            elif mode == "print-wrappers":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonWrappers](Span(raw))
                out += encode_json(message)
            elif mode == "parse-timestamp":
                var message = decode_json[Timestamp](line)
                out += to_hex(encode(message))
            elif mode == "print-timestamp":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[Timestamp](Span(raw))
                out += encode_json(message)
            elif mode == "parse-timestamp-parent":
                var message = decode_json[JsonTimestamp](line)
                out += to_hex(encode(message))
            elif mode == "print-timestamp-parent":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonTimestamp](Span(raw))
                out += encode_json(message)
            elif mode == "parse-duration":
                var message = decode_json[Duration](line)
                out += to_hex(encode(message))
            elif mode == "print-duration":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[Duration](Span(raw))
                out += encode_json(message)
            elif mode == "parse-duration-parent":
                var message = decode_json[JsonDuration](line)
                out += to_hex(encode(message))
            elif mode == "print-duration-parent":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonDuration](Span(raw))
                out += encode_json(message)
            elif mode == "parse-field-mask":
                var message = decode_json[FieldMask](line)
                out += to_hex(encode(message))
            elif mode == "print-field-mask":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[FieldMask](Span(raw))
                out += encode_json(message)
            elif mode == "parse-field-mask-parent":
                var message = decode_json[JsonFieldMask](line)
                out += to_hex(encode(message))
            elif mode == "print-field-mask-parent":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonFieldMask](Span(raw))
                out += encode_json(message)
            elif mode == "parse-struct":
                var message = decode_json[Struct](line)
                out += to_hex(encode(message))
            elif mode == "print-struct":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[Struct](Span(raw))
                out += encode_json(message)
            elif mode == "parse-value":
                var message = decode_json[Value](line)
                out += to_hex(encode(message))
            elif mode == "print-value":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[Value](Span(raw))
                out += encode_json(message)
            elif mode == "parse-list-value":
                var message = decode_json[ListValue](line)
                out += to_hex(encode(message))
            elif mode == "print-list-value":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[ListValue](Span(raw))
                out += encode_json(message)
            elif mode == "parse-struct-values":
                var message = decode_json[JsonStructValues](line)
                out += to_hex(encode(message))
            elif mode == "print-struct-values":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonStructValues](Span(raw))
                out += encode_json(message)
            elif mode == "parse-descriptor-messages":
                var message = decode_json[JsonDescriptorMessages](line)
                out += to_hex(encode(message))
            elif mode == "print-descriptor-messages":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[JsonDescriptorMessages](Span(raw))
                out += encode_json(message)
            elif mode == "parse-tree":
                var message = decode_json[Tree](line)
                out += to_hex(encode(message))
            elif mode == "print-tree":
                var raw = List[Byte]()
                var encoded = String(line.strip())
                if encoded != "-":
                    raw = from_hex(encoded)
                var message = decode[Tree](Span(raw))
                out += encode_json(message)
            else:
                raise Error("unknown mode")
        except e:
            out += "ERR " + String(e)
        out += "\n"
    return out^


def main() raises:
    var args = argv()
    if len(args) != 4:
        raise Error("usage: proto_json_codec <parse|print> <infile> <outfile>")
    var infile = open(String(args[2]), "r")
    var text = infile.read()
    infile.close()
    var result = run(args[1], text)
    var outfile = open(String(args[3]), "w")
    outfile.write_all(result.as_bytes())
    outfile.close()
