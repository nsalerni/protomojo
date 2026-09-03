#!/usr/bin/env python3
"""Check generated gRPC service registration helpers."""

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "tools" / "protoc-gen-mojo"


ECHO_PROTO = """syntax = "proto3";

package echo;

message EchoRequest { string message = 1; }
message EchoResponse { string message = 1; }

service Echo {
  rpc Say(EchoRequest) returns (EchoResponse);
  rpc Split(EchoRequest) returns (stream EchoResponse);
  rpc Join(stream EchoRequest) returns (EchoResponse);
  rpc Chat(stream EchoRequest) returns (stream EchoResponse);
}
"""


def generate(proto: Path, output: Path) -> str:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"-I{proto.parent}",
            f"--plugin=protoc-gen-mojo={PLUGIN}",
            f"--mojo_out={output}",
            str(proto),
        ],
        cwd=ROOT,
        check=True,
    )
    return (output / (proto.stem + "_pb.mojo")).read_text()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="protomojo-grpc-codegen-") as temp:
        root = Path(temp)
        proto = root / "echo.proto"
        proto.write_text(ECHO_PROTO)
        source = generate(proto, root)

        assert "PollingServer," in source
        assert "def add_echo_service[" in source
        assert "](mut server: Server):" in source
        assert "def add_echo_polling_service[" in source
        assert "](mut server: PollingServer):" in source
        assert "server.register_unary[say](ECHO_SAY_PATH)" in source
        assert "server.register_server_streaming[split](ECHO_SPLIT_PATH)" in source
        assert "server.register_client_streaming[join](ECHO_JOIN_PATH)" in source
        assert "server.register_bidi[chat](ECHO_CHAT_PATH)" in source
        assert source.count("server.register_unary[say](ECHO_SAY_PATH)") == 2
        assert "say: def (EchoRequest, mut ServerContext) raises thin -> EchoResponse," in source

    print("test_grpc_codegen: all tests passed")


if __name__ == "__main__":
    main()
