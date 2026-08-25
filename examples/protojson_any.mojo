from std.testing import assert_equal, assert_true

from any_pb import Any
from proto import (
    JsonParseOptions,
    JsonPrintOptions,
    decode,
    decode_json,
    encode,
    encode_json,
)
from protojson_any_pb import AuditEvent, Envelope
from protojson_any_pb_json_resolver import json_type_resolver


def main() raises:
    var event = AuditEvent()
    event.id = 42
    event.action = "signed in"

    var wrapped = Any()
    wrapped.type_url = (
        "type.googleapis.com/protomojo.examples.AuditEvent"
    )
    wrapped.value = encode(event)

    var envelope = Envelope()
    envelope.event = wrapped^

    var text = encode_json(
        envelope,
        options=JsonPrintOptions(type_resolver=json_type_resolver()),
    )
    assert_equal(
        text,
        '{"event":{"@type":"type.googleapis.com/'
        'protomojo.examples.AuditEvent","id":"42",'
        '"action":"signed in"}}',
    )

    var parsed = decode_json[Envelope](
        text,
        options=JsonParseOptions(type_resolver=json_type_resolver()),
    )
    assert_true(Bool(parsed.event))
    var unpacked = decode[AuditEvent](Span(parsed.event.value().value))
    assert_equal(unpacked.id, UInt64(42))
    assert_equal(unpacked.action, "signed in")

    print(text)
