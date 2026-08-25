# Compliance tool for generated proto3 JSON messages.
#
# Usage: proto_json_codec <mode> <infile> <outfile>
#
# Parse modes accept one JSON object per line and write protobuf bytes as hex.
# Print modes accept one hex protobuf message per line and write one JSON object.

from std.sys import argv

from proto import JsonParseOptions, decode, decode_json, encode, encode_json
from empty_pb import Empty
from testutil import from_hex, to_hex
from vectors_pb import (
    EnumValue,
    JsonEmptyParent,
    JsonKeyMaps,
    JsonMessageMaps,
    JsonOneof,
    JsonOptional,
    JsonParent,
    JsonRepeated,
    JsonRepeatedMessages,
    JsonStringMaps,
    Scalars,
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
