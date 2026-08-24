from std.testing import assert_equal

from package_smoke_pb import PackageSmoke
from proto import decode, decode_json, encode, encode_json


def main() raises:
    var sent = PackageSmoke()
    sent.request_id = 42
    sent.payload = "installed package"

    var received = decode[PackageSmoke](Span(encode(sent)))
    assert_equal(received.request_id, 42)
    assert_equal(received.payload, "installed package")

    var json_received = decode_json[PackageSmoke](encode_json(sent))
    assert_equal(json_received.request_id, 42)
    assert_equal(json_received.payload, "installed package")
    print("protomojo package smoke test passed")
