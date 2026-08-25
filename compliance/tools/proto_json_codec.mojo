# Compliance tool for generated proto3 JSON messages.
#
# Usage: proto_json_codec <mode> <infile> <outfile>
#
# Parse modes accept one JSON object per line and write protobuf bytes as hex.
# Print modes accept one hex protobuf message per line and write one JSON object.

from std.sys import argv

from proto import JsonParseOptions, decode, decode_json, encode, encode_json
from testutil import from_hex, to_hex
from vectors_pb import (
    EnumValue,
    JsonParent,
    JsonRepeated,
    JsonRepeatedMessages,
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
