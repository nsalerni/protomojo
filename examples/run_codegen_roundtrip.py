#!/usr/bin/env python3
"""Regenerate and run the address-book example."""

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="protomojo-example-") as temp:
        output = Path(temp)
        run(
            [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"-I{EXAMPLES}",
                f"--plugin=protoc-gen-mojo={ROOT / 'tools' / 'protoc-gen-mojo'}",
                f"--mojo_out={output}",
                str(EXAMPLES / "address_book.proto"),
            ]
        )

        run(
            [
                "mojo",
                "run",
                "-I",
                str(ROOT / "src"),
                "-I",
                str(output),
                str(EXAMPLES / "codegen_roundtrip.mojo"),
            ]
        )


if __name__ == "__main__":
    main()
