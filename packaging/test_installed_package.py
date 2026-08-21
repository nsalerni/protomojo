#!/usr/bin/env python3
"""Build the conda package and run its tests in a clean environment."""

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHANNELS = ["https://conda.modular.com/max", "conda-forge"]


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="protomojo-package-") as temp:
        output = Path(temp) / "dist"
        run(
            [
                "pixi",
                "publish",
                "--path",
                str(ROOT),
                "--target-dir",
                str(output),
            ]
        )

        packages = sorted(output.glob("protomojo-*.conda"))
        if len(packages) != 1:
            raise RuntimeError(
                f"expected one protomojo package, found {len(packages)}"
            )

        command = [
            "pixi",
            "exec",
            "--spec",
            "rattler-build>=0.30,<0.31",
            "rattler-build",
            "test",
            "--package-file",
            str(packages[0]),
        ]
        for channel in CHANNELS:
            command.extend(["--channel", channel])
        run(command)


if __name__ == "__main__":
    main()
