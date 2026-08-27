# Decode and re-encode proto3 JSON for the JSON mutation runner.
#
# Usage: proto_json_probe <kind> <infile> <outfile>
#   kind:    maps|oneof|any|nested
#   infile:  one hex-encoded UTF-8 JSON object per line, or "-" for empty text
#   outfile: one "OK <hex>" or "ERR" result per input line

from std.sys import argv

from proto import (
    JsonParseOptions,
    JsonPrintOptions,
    decode_json,
    encode_json,
)
from testutil import from_hex, to_hex
from vectors_pb import JsonAnyParent, JsonOneof, JsonStringMaps, Nested
from vectors_pb_json_resolver import json_type_resolver


def parse_options() -> JsonParseOptions:
    """Returns parse options with the generated Any type resolver."""
    return JsonParseOptions(type_resolver=json_type_resolver())


def print_options() -> JsonPrintOptions:
    """Returns print options with the generated Any type resolver."""
    return JsonPrintOptions(type_resolver=json_type_resolver())


def reencode(kind: StringSpan, text: StringSpan) raises -> String:
    """Parses one supported JSON kind and returns its encoded JSON bytes."""
    var parsed: String
    if kind == "maps":
        parsed = encode_json(
            decode_json[JsonStringMaps](text, options=parse_options()),
            options=print_options(),
        )
    elif kind == "oneof":
        parsed = encode_json(
            decode_json[JsonOneof](text, options=parse_options()),
            options=print_options(),
        )
    elif kind == "any":
        parsed = encode_json(
            decode_json[JsonAnyParent](text, options=parse_options()),
            options=print_options(),
        )
    elif kind == "nested":
        parsed = encode_json(
            decode_json[Nested](text, options=parse_options()),
            options=print_options(),
        )
    else:
        raise Error("unknown message kind")
    var encoded = List[Byte]()
    encoded.extend(parsed.as_bytes())
    return to_hex(Span(encoded))


def run(kind: StringSpan, text: String) raises -> String:
    """Processes each input line, including empty JSON text encoded as "-"."""
    var out = String()
    for line in text.split("\n"):
        var stripped = line.strip()
        if stripped.byte_length() == 0:
            continue
        try:
            # "-" is empty UTF-8 from the mutation runner. Empty JSON is
            # invalid; do not map it to "{}".
            if stripped == "-":
                out += "OK " + reencode(kind, "")
            else:
                var raw = from_hex(stripped)
                out += "OK " + reencode(kind, String(from_utf8=raw))
        except:
            out += "ERR"
        out += "\n"
    return out^


def main() raises:
    var args = argv()
    if len(args) != 4:
        raise Error("usage: proto_json_probe <kind> <infile> <outfile>")
    var infile = open(String(args[2]), "r")
    var text = infile.read()
    infile.close()
    var result = run(args[1], text)
    var outfile = open(String(args[3]), "w")
    outfile.write_all(result.as_bytes())
    outfile.close()
