# Compliance tool: decode + re-encode protobuf messages.
#
# Usage: proto_codec <scalars|nested|tree> <infile> <outfile>
#   infile:  one hex-encoded message per line
#   outfile: for each input, the hex of decode->re-encode, or "ERR <msg>"
#
# The compliance runner feeds messages produced by the reference Python
# protobuf implementation and checks our re-encoding parses back equal.

from std.sys import argv

from proto import decode, encode
from testutil import from_hex, to_hex
from vectors_pb import Nested, Scalars, Tree


def run(kind: StringSpan, text: String) raises -> String:
    var out = String()
    for line in text.split("\n"):
        var stripped = line.strip()
        if stripped.byte_length() == 0:
            continue
        try:
            var raw = from_hex(stripped)
            if kind == "scalars":
                var m = decode[Scalars](Span(raw))
                out += to_hex(encode(m))
            elif kind == "nested":
                var m = decode[Nested](Span(raw))
                out += to_hex(encode(m))
            elif kind == "tree":
                var m = decode[Tree](Span(raw))
                out += to_hex(encode(m))
            else:
                raise Error("unknown message kind")
        except e:
            out += "ERR " + String(e)
        out += "\n"
    return out^


def main() raises:
    var args = argv()
    if len(args) != 4:
        raise Error("usage: proto_codec <kind> <infile> <outfile>")
    var infile = open(String(args[2]), "r")
    var text = infile.read()
    infile.close()
    var result = run(args[1], text)
    var outfile = open(String(args[3]), "w")
    outfile.write_all(result.as_bytes())
    outfile.close()
