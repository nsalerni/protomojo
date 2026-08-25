#!/usr/bin/env python3
"""Mutate protobuf binary messages and compare protomojo with protobuf."""

from __future__ import annotations

import argparse
import importlib
import json
import random
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GOLDEN_VECTORS = ROOT / "test" / "proto_golden.mojo"
PROTO_SCHEMA = ROOT / "test" / "vectors.proto"
PROBE_SOURCE = ROOT / "fuzz" / "proto_wire_probe.mojo"
DEFAULT_FAILURE_OUTPUT = ROOT / "build" / "wire-fuzz-failure.json"
DEFAULT_SEED = 20260824
DEFAULT_CASES = 250
MAX_SEED = (1 << 32) - 1
MAX_CASES = 100_000
MAX_INPUT_BYTES = 4096

# These are the malformed binary cases in the compliance suite. Keeping the
# names here makes a saved failure useful without requiring its case index.
MALFORMED_SEEDS = (
    ("missing_varint_value", "08"),
    ("overlong_varint", "0880808080808080808080"),
    ("short_length_delimited", "0a05616263"),
    ("short_fixed32", "1d0000"),
    ("unexpected_end_group", "0c00"),
    ("field_number_above_max", "0dff808080808080ffff0142"),
)


@dataclass(frozen=True)
class WireSeed:
    """One checked-in payload and the generated message type that parses it."""

    name: str
    kind: str
    payload: bytes


@dataclass(frozen=True)
class MutationCase:
    """One deterministic payload derived from a checked-in seed."""

    index: int
    base_name: str
    kind: str
    operations: tuple[str, ...]
    payload: bytes


def bounded_int(text: str, minimum: int, maximum: int) -> int:
    """Parses one bounded integer command-line value."""
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value < minimum or value > maximum:
        raise argparse.ArgumentTypeError(
            f"must be between {minimum} and {maximum}"
        )
    return value


def parse_args() -> argparse.Namespace:
    """Parses the fixed-seed mutation run settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed",
        type=lambda text: bounded_int(text, 0, MAX_SEED),
        default=DEFAULT_SEED,
    )
    parser.add_argument(
        "--cases",
        type=lambda text: bounded_int(text, 1, MAX_CASES),
        default=DEFAULT_CASES,
    )
    parser.add_argument(
        "--failure-output",
        type=Path,
        default=DEFAULT_FAILURE_OUTPUT,
        help="path for the first failing input",
    )
    args = parser.parse_args()
    return args


def load_golden_seeds() -> list[WireSeed]:
    """Loads every supported binary vector from the generated Mojo constants."""
    text = GOLDEN_VECTORS.read_text()
    constants = re.findall(r'^comptime ([A-Z0-9_]+) = "([0-9a-f]*)"$', text, re.MULTILINE)
    seeds: list[WireSeed] = []
    for name, payload_hex in constants:
        if name.startswith("SCALARS_"):
            kind = "scalars"
        elif name.startswith("NESTED_"):
            kind = "nested"
        elif name == "ECHO_PING":
            kind = "echo"
        else:
            continue
        seeds.append(WireSeed(name.lower(), kind, bytes.fromhex(payload_hex)))
    if not seeds:
        raise RuntimeError(f"no supported golden vectors found in {GOLDEN_VECTORS}")
    return seeds


def load_seed_corpus() -> list[WireSeed]:
    """Combines reference-generated golden bytes with malformed compliance cases."""
    seeds = load_golden_seeds()
    seeds.extend(
        WireSeed(f"malformed_{name}", "scalars", bytes.fromhex(payload_hex))
        for name, payload_hex in MALFORMED_SEEDS
    )
    return seeds


def random_bytes(rng: random.Random, count: int) -> bytes:
    """Returns deterministic bytes without depending on platform APIs."""
    return bytes(rng.randrange(256) for _ in range(count))


def mutate_once(
    payload: bytes,
    rng: random.Random,
    corpus: list[WireSeed],
) -> tuple[bytes, str]:
    """Applies one bounded wire-level mutation."""
    data = bytearray(payload)
    operation = rng.randrange(8)

    if operation == 0 and data:
        offset = rng.randrange(len(data))
        bit = 1 << rng.randrange(8)
        data[offset] ^= bit
        return bytes(data), f"flip_bit@{offset}:{bit}"

    if operation == 1 and data:
        offset = rng.randrange(len(data))
        value = rng.randrange(256)
        data[offset] = value
        return bytes(data), f"replace_byte@{offset}:{value}"

    if operation == 2:
        offset = rng.randrange(len(data) + 1)
        inserted = random_bytes(rng, rng.randint(1, 8))
        data[offset:offset] = inserted
        return bytes(data[:MAX_INPUT_BYTES]), f"insert@{offset}:{inserted.hex()}"

    if operation == 3 and data:
        start = rng.randrange(len(data))
        count = rng.randint(1, min(8, len(data) - start))
        del data[start : start + count]
        return bytes(data), f"delete@{start}:{count}"

    if operation == 4 and data:
        length = rng.randrange(len(data))
        return bytes(data[:length]), f"truncate:{length}"

    if operation == 5:
        appended = random_bytes(rng, rng.randint(1, 8))
        data.extend(appended)
        return bytes(data[:MAX_INPUT_BYTES]), f"append:{appended.hex()}"

    if operation == 6:
        donor = corpus[rng.randrange(len(corpus))]
        if donor.payload:
            start = rng.randrange(len(donor.payload))
            count = rng.randint(1, min(8, len(donor.payload) - start))
            offset = rng.randrange(len(data) + 1)
            fragment = donor.payload[start : start + count]
            data[offset:offset] = fragment
            return bytes(data[:MAX_INPUT_BYTES]), (
                f"splice@{offset}:{donor.name}[{start}:{start + count}]"
            )

    if data:
        start = rng.randrange(len(data))
        count = rng.randint(1, min(10, len(data) - start))
        value = rng.choice((0x00, 0x7F, 0x80, 0xFF))
        data[start : start + count] = bytes([value]) * count
        return bytes(data), f"fill@{start}:{count}:{value}"

    value = rng.randrange(256)
    return bytes([value]), f"insert@0:{value:02x}"


def make_cases(seed: int, count: int, corpus: list[WireSeed]) -> list[MutationCase]:
    """Builds a deterministic case list that cycles through the whole corpus."""
    rng = random.Random(seed)
    order = list(corpus)
    rng.shuffle(order)
    cases: list[MutationCase] = []
    for index in range(count):
        base = order[index % len(order)]
        payload = base.payload
        operations: list[str] = []
        for _ in range(rng.randint(1, 3)):
            payload, description = mutate_once(payload, rng, corpus)
            operations.append(description)
        cases.append(
            MutationCase(index, base.name, base.kind, tuple(operations), payload)
        )
    return cases


def compile_python_messages(output_dir: Path):
    """Generates the Python protobuf classes used as the external oracle."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"-I{PROTO_SCHEMA.parent}",
            f"--python_out={output_dir}",
            str(PROTO_SCHEMA),
        ],
        check=True,
        cwd=ROOT,
    )
    sys.path.insert(0, str(output_dir))
    vectors_pb2 = importlib.import_module("vectors_pb2")

    return {
        "scalars": vectors_pb2.Scalars,
        "nested": vectors_pb2.Nested,
        "echo": vectors_pb2.EchoRequest,
    }


def build_probe(output_path: Path) -> None:
    """Builds the Mojo decode and re-encode probe once per fuzz run."""
    subprocess.run(
        [
            "mojo",
            "build",
            "-I",
            "src",
            "-I",
            "test",
            str(PROBE_SOURCE.relative_to(ROOT)),
            "-o",
            str(output_path),
        ],
        check=True,
        cwd=ROOT,
    )


def run_probe(
    binary: Path,
    cases: list[MutationCase],
    work_dir: Path,
) -> dict[int, str]:
    """Runs one Mojo process per message kind and keeps original case order."""
    results: dict[int, str] = {}
    for kind in ("scalars", "nested", "echo"):
        selected = [case for case in cases if case.kind == kind]
        if not selected:
            continue
        input_path = work_dir / f"{kind}.in"
        output_path = work_dir / f"{kind}.out"
        input_path.write_text(
            "".join((case.payload.hex() or "-") + "\n" for case in selected)
        )
        completed = subprocess.run(
            [str(binary), kind, str(input_path), str(output_path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=ROOT,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Mojo probe failed for {kind}: {detail[:400]}")
        lines = output_path.read_text().splitlines()
        if len(lines) != len(selected):
            raise RuntimeError(
                f"Mojo probe returned {len(lines)} {kind} rows for {len(selected)} inputs"
            )
        results.update((case.index, line) for case, line in zip(selected, lines))
    return results


def python_parse(message_type, payload: bytes):
    """Returns a parsed reference message or the reference parse error."""
    message = message_type()
    try:
        message.ParseFromString(payload)
    except Exception as error:
        return None, error
    return message, None


def save_failure(
    path: Path,
    *,
    seed: int,
    total_cases: int,
    case: MutationCase,
    reason: str,
    python_accepted: bool,
    mojo_result: str,
) -> None:
    """Writes the first failure in a stable, directly reproducible format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "version": 1,
        "seed": seed,
        "cases": total_cases,
        "case_index": case.index,
        "message_kind": case.kind,
        "base_seed": case.base_name,
        "operations": list(case.operations),
        "input_hex": case.payload.hex(),
        "python_accepted": python_accepted,
        "mojo_result": mojo_result,
        "reason": reason,
    }
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def evaluate(
    cases: list[MutationCase],
    probe_results: dict[int, str],
    message_types,
    *,
    seed: int,
    failure_output: Path,
) -> int:
    """Checks acceptance and semantics against Python protobuf."""
    valid_agreements = 0
    malformed_agreements = 0

    for case in cases:
        expected, parse_error = python_parse(message_types[case.kind], case.payload)
        result = probe_results[case.index]
        mojo_accepted = result.startswith("OK ")

        reason = ""
        if parse_error is not None:
            if mojo_accepted:
                reason = "Python protobuf rejected the input but protomojo accepted it"
            else:
                malformed_agreements += 1
                continue
        elif not mojo_accepted:
            reason = "Python protobuf accepted the input but protomojo rejected it"
        else:
            encoded_hex = result[3:]
            try:
                encoded = bytes.fromhex(encoded_hex)
            except ValueError:
                reason = "the Mojo probe returned invalid hexadecimal output"
            else:
                actual, output_error = python_parse(message_types[case.kind], encoded)
                if output_error is not None:
                    reason = "Python protobuf rejected the protomojo re-encoding"
                elif actual != expected:
                    reason = "Python protobuf found a semantic mismatch after re-encoding"
                else:
                    valid_agreements += 1
                    continue

        save_failure(
            failure_output,
            seed=seed,
            total_cases=len(cases),
            case=case,
            reason=reason,
            python_accepted=parse_error is None,
            mojo_result=result,
        )
        print(f"FAIL case={case.index} kind={case.kind} base={case.base_name}")
        print(f"reason: {reason}")
        print(f"saved first failing input: {failure_output}")
        return 1

    print(f"valid semantic agreement: {valid_agreements} cases")
    print(f"malformed rejection agreement: {malformed_agreements} cases")
    print(f"PASS total agreement: {valid_agreements + malformed_agreements}/{len(cases)}")
    return 0


def main() -> int:
    """Builds both oracles once, runs mutations, and reports exact counts."""
    args = parse_args()
    failure_output = args.failure_output.resolve()
    failure_output.unlink(missing_ok=True)
    corpus = load_seed_corpus()
    cases = make_cases(args.seed, args.cases, corpus)

    print(
        f"protobuf wire fuzz: seed={args.seed} cases={args.cases} "
        f"corpus={len(corpus)} max_input_bytes={MAX_INPUT_BYTES}"
    )
    with tempfile.TemporaryDirectory(prefix="protomojo-wire-fuzz-") as tmp:
        work_dir = Path(tmp)
        message_types = compile_python_messages(work_dir)
        probe = work_dir / "proto_wire_probe"
        build_probe(probe)
        try:
            probe_results = run_probe(probe, cases, work_dir)
        except Exception as error:
            first = cases[0]
            save_failure(
                failure_output,
                seed=args.seed,
                total_cases=len(cases),
                case=first,
                reason=str(error),
                python_accepted=False,
                mojo_result="probe failure",
            )
            print(f"FAIL: {error}")
            print(f"saved first failing input: {failure_output}")
            return 1
        return evaluate(
            cases,
            probe_results,
            message_types,
            seed=args.seed,
            failure_output=failure_output,
        )


if __name__ == "__main__":
    sys.exit(main())
