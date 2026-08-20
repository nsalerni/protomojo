# Google protobuf conformance-suite testee for the `proto` package.
#
# Speaks the conformance runner's pipe protocol on stdin/stdout:
#   <4-byte LE length><ConformanceRequest> in,
#   <4-byte LE length><ConformanceResponse> out, until EOF.
#
# Binary wire format only: JSON/text/jspb requests are answered with
# `skipped` (the runner accepts skips; they are counted, not failed).
#
# stdout is the protocol channel — nothing may print.

from conformance_pb import ConformanceRequest, ConformanceResponse
from test_messages_proto3_pb import TestAllTypesProto3
from proto import decode, encode


def read_exact(
    mut stdin: FileDescriptor, n: Int
) raises -> Optional[List[Byte]]:
    var out = List[Byte]()
    while len(out) < n:
        var buf = List[Byte]()
        buf.resize(n - len(out), 0)
        var got = stdin.read_bytes(Span(buf))
        if got <= 0:
            if len(out) == 0:
                return None  # clean EOF between messages
            raise Error("conformance: truncated pipe message")
        out.extend(Span(buf)[0:got])
    return out^


def handle(request: ConformanceRequest) raises -> ConformanceResponse:
    var resp = ConformanceResponse()
    # Only binary protobuf in...
    if request.payload_case != 1:
        resp.skipped = "only the binary wire format is implemented"
        resp.result_case = 5
        return resp^
    # ...and only binary protobuf out (WireFormat.PROTOBUF == 1).
    if request.requested_output_format != 1:
        resp.skipped = "only the binary wire format is implemented"
        resp.result_case = 5
        return resp^
    if (
        request.message_type
        != "protobuf_test_messages.proto3.TestAllTypesProto3"
    ):
        resp.skipped = "only TestAllTypesProto3 is implemented"
        resp.result_case = 5
        return resp^
    var msg: TestAllTypesProto3
    try:
        msg = decode[TestAllTypesProto3](Span(request.protobuf_payload))
    except e:
        resp.parse_error = String(e)
        resp.result_case = 1
        return resp^
    resp.protobuf_payload = encode(msg)
    resp.result_case = 3
    return resp^


def main() raises:
    var stdin = FileDescriptor(0)
    var stdout = FileDescriptor(1)
    while True:
        var header = read_exact(stdin, 4)
        if not header:
            return  # runner closed the pipe: done
        var hdr = header.take()
        var n = (
            Int(hdr[0])
            | (Int(hdr[1]) << 8)
            | (Int(hdr[2]) << 16)
            | (Int(hdr[3]) << 24)
        )
        var body = read_exact(stdin, n)
        if not body:
            raise Error("conformance: missing request body")
        var request = decode[ConformanceRequest](Span(body.value()))
        var resp: ConformanceResponse
        try:
            resp = handle(request)
        except e:
            resp = ConformanceResponse()
            resp.runtime_error = String(e)
            resp.result_case = 2
        var payload = encode(resp)
        var out = List[Byte](capacity=4 + len(payload))
        var m = len(payload)
        out.append(UInt8(m & 0xFF))
        out.append(UInt8((m >> 8) & 0xFF))
        out.append(UInt8((m >> 16) & 0xFF))
        out.append(UInt8((m >> 24) & 0xFF))
        out.extend(Span(payload))
        stdout.write_bytes(Span(out))
