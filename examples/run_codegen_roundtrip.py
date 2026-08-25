#!/usr/bin/env python3
"""Regenerate and run the code generation examples."""

import subprocess
import sys
import tempfile
from pathlib import Path

import grpc_tools


ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
PLUGIN = ROOT / "tools" / "protoc-gen-mojo"


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="protomojo-example-") as temp:
        output = Path(temp)
        protobuf_include = Path(grpc_tools.__file__).parent / "_proto"
        run(
            [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"-I{EXAMPLES}",
                f"--plugin=protoc-gen-mojo={PLUGIN}",
                f"--mojo_out={output}",
                str(EXAMPLES / "address_book.proto"),
            ]
        )

        run(
            [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"-I{EXAMPLES}",
                f"-I{protobuf_include}",
                f"--plugin=protoc-gen-mojo={PLUGIN}",
                f"--mojo_out={output}",
                str(EXAMPLES / "protojson_any.proto"),
            ]
        )

        for source in ("codegen_roundtrip.mojo", "protojson_any.mojo"):
            run(
                [
                    "mojo",
                    "run",
                    "-I",
                    str(ROOT / "src"),
                    "-I",
                    str(output),
                    str(EXAMPLES / source),
                ]
            )


if __name__ == "__main__":
    main()
