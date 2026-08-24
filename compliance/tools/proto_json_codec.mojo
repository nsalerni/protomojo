# Compliance tool for generated flat primitive proto3 JSON messages.
#
# Usage: proto_json_codec <parse|print> <infile> <outfile>
#
# parse accepts one JSON object per line and writes its protobuf bytes as hex.
# print accepts one hex protobuf message per line and writes one JSON object.

from std.sys import argv

from proto import decode, decode_json, encode, encode_json
from testutil import from_hex, to_hex
from vectors_pb import Scalars


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
