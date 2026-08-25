# Google protobuf conformance-suite testee for the `proto` package.
#
# Speaks the conformance runner's pipe protocol on stdin/stdout:
#   <4-byte LE length><ConformanceRequest> in,
#   <4-byte LE length><ConformanceResponse> out, until EOF.
#
# Binary wire and proto3 JSON are supported. Text and jspb requests are
# answered with `skipped`.
#
# stdout is the protocol channel. Nothing may print.

from conformance_pb import ConformanceRequest, ConformanceResponse
from test_messages_proto3_pb import TestAllTypesProto3
from test_messages_proto3_pb_json_resolver import json_type_resolver
from proto import (
    JsonParseOptions,
    JsonPrintOptions,
    decode,
    decode_json,
    encode,
    encode_json,
)


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
    if (
        request.message_type
        != "protobuf_test_messages.proto3.TestAllTypesProto3"
    ):
        resp.skipped = "only TestAllTypesProto3 is implemented"
        resp.result_case = 5
        return resp^
    if (
        request.requested_output_format != 1
        and request.requested_output_format != 2
    ):
        resp.skipped = "only binary and JSON output are implemented"
        resp.result_case = 5
        return resp^

    var parse_options = JsonParseOptions(
        ignore_unknown_fields=request.test_category == 3,
        type_resolver=json_type_resolver(),
    )
    var msg: TestAllTypesProto3
    try:
        if request.payload_case == 1:
            msg = decode[TestAllTypesProto3](Span(request.protobuf_payload))
        elif request.payload_case == 2:
            msg = decode_json[TestAllTypesProto3](
                request.json_payload, options=parse_options
            )
        else:
            resp.skipped = "only binary and JSON input are implemented"
            resp.result_case = 5
            return resp^
    except e:
        resp.parse_error = String(e)
        resp.result_case = 1
        return resp^

    try:
        if request.requested_output_format == 1:
            resp.protobuf_payload = encode(msg)
            resp.result_case = 3
        elif request.requested_output_format == 2:
            var print_options = JsonPrintOptions(
                type_resolver=json_type_resolver()
            )
            resp.json_payload = encode_json(msg, options=print_options)
            resp.result_case = 4
    except e:
        resp.serialize_error = String(e)
        resp.result_case = 6
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
