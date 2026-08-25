# Decode and re-encode protobuf messages for the wire mutation runner.
#
# Usage: proto_wire_probe <scalars|nested|echo> <infile> <outfile>
#   infile:  one hex-encoded message per line, or "-" for an empty message
#   outfile: one "OK <hex>" or "ERR" result per input line

from std.sys import argv

from proto import decode, encode
from testutil import from_hex, to_hex
from vectors_pb import EchoRequest, Nested, Scalars


def reencode(kind: StringSpan, raw: Span[Byte, _]) raises -> String:
    """Decodes one supported message kind and returns its encoded bytes."""
    if kind == "scalars":
        return to_hex(encode(decode[Scalars](raw)))
    if kind == "nested":
        return to_hex(encode(decode[Nested](raw)))
    if kind == "echo":
        return to_hex(encode(decode[EchoRequest](raw)))
    raise Error("unknown message kind")


def run(kind: StringSpan, text: String) raises -> String:
    """Processes each input line without dropping empty protobuf messages."""
    var out = String()
    for line in text.split("\n"):
        var stripped = line.strip()
        if stripped.byte_length() == 0:
            continue
        try:
            if stripped == "-":
                var raw = List[Byte]()
                out += "OK " + reencode(kind, Span(raw))
            else:
                var raw = from_hex(stripped)
                out += "OK " + reencode(kind, Span(raw))
        except:
            out += "ERR"
        out += "\n"
    return out^


def main() raises:
    var args = argv()
    if len(args) != 4:
        raise Error("usage: proto_wire_probe <kind> <infile> <outfile>")
    var infile = open(String(args[2]), "r")
    var text = infile.read()
    infile.close()
    var result = run(args[1], text)
    var outfile = open(String(args[3]), "w")
    outfile.write_all(result.as_bytes())
    outfile.close()
