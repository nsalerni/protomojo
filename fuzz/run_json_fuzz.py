#!/usr/bin/env python3
"""Mutate proto3 JSON messages and compare protomojo with protobuf."""

from __future__ import annotations

import argparse
import importlib
import json
import random
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from google.protobuf import json_format


ROOT = Path(__file__).resolve().parent.parent
PROTO_SCHEMA = ROOT / "test" / "vectors.proto"
PROBE_SOURCE = ROOT / "fuzz" / "proto_json_probe.mojo"
DEFAULT_FAILURE_OUTPUT = ROOT / "build" / "json-fuzz-failure.json"
DEFAULT_SEED = 20260827
DEFAULT_CASES = 250
MAX_SEED = (1 << 32) - 1
MAX_CASES = 100_000
MAX_INPUT_BYTES = 4096
JSON_ALPHABET = '{}[]":,.-+eEtruefalsn0123456789_abcdefghijklmnopqrstuvwxyz'

MALFORMED_SEEDS = (
    ("unclosed_object", "{"),
    ("array_root", "[]"),
    ("json_null", "null"),
    ("true_root", "true"),
    ("unknown_field", '{"notAField":1}'),
    ("duplicate_member", '{"stringValue":"a","stringValue":"b"}'),
    ("null_map_entry", '{"int32Values":{"k":null}}'),
)


@dataclass(frozen=True)
class JsonSeed:
    """One JSON payload and the generated message type that parses it."""

    name: str
    kind: str
    text: str


@dataclass(frozen=True)
class MutationCase:
    """One deterministic JSON payload derived from a checked-in seed."""

    index: int
    base_name: str
    kind: str
    operations: tuple[str, ...]
    text: str


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
    return parser.parse_args()


def json_text(message) -> str:
    """Prints one protobuf message with the default proto3 JSON mapping."""
    return json_format.MessageToJson(message)


def shape_seeds(vectors_pb2) -> list[JsonSeed]:
    """Builds well-known, map, oneof, Any, and nested JSON payloads."""
    maps = vectors_pb2.JsonStringMaps()
    maps.int32_values["one"] = 1
    maps.int32_values["two"] = 2
    maps.string_values["k"] = "v"
    maps.bool_values["on"] = True
    maps.status_values["active"] = vectors_pb2.STATUS_ACTIVE

    text = vectors_pb2.JsonOneof()
    text.string_value = "chosen"
    number = vectors_pb2.JsonOneof()
    number.int64_value = -9
    child = vectors_pb2.JsonOneof()
    child.child_value.id = 4
    child.child_value.note = "json"

    payload = vectors_pb2.JsonAnyPayload(id=11, note="packed")
    any_parent = vectors_pb2.JsonAnyParent()
    any_parent.value.Pack(payload)
    any_parent.values.add().Pack(payload)
    any_parent.mapped["entry"].Pack(payload)

    nested = vectors_pb2.Nested()
    nested.inner.f_int32 = 8
    nested.names.append("a")
    nested.counts["one"] = 1
    nested.as_text = "chosen"

    timestamp = vectors_pb2.JsonTimestamp()
    timestamp.value.seconds = 1484443815
    timestamp.value.nanos = 10_000_000

    duration = vectors_pb2.JsonDuration()
    duration.value.seconds = 1
    duration.value.nanos = 500_000_000
    extra_duration = duration.values.add()
    extra_duration.seconds = -3
    extra_duration.nanos = -250_000_000

    field_mask = vectors_pb2.JsonFieldMask()
    field_mask.value.paths.extend(["foo_bar", "outer.inner_field"])
    field_mask.values.add().paths.append("a.b")

    wrappers = vectors_pb2.JsonWrappers()
    wrappers.double_value.value = 1.5
    wrappers.int64_value.value = -9
    wrappers.bool_value.value = True
    wrappers.string_value.value = "wrapped"
    wrappers.bytes_value.value = b"abc"

    struct_values = json_format.ParseDict(
        {
            "structValue": {"k": "v", "n": 1},
            "value": True,
            "listValue": [2, "x"],
            "values": [{"a": 1}, "t"],
            "text": "chosen",
            "mapped": {"entry": {"inner": False}},
            "selected": 3,
            "optionalValue": "opt",
        },
        vectors_pb2.JsonStructValues(),
    )

    return [
        JsonSeed("maps_populated", "maps", json_text(maps)),
        JsonSeed("maps_empty", "maps", "{}"),
        JsonSeed("oneof_text", "oneof", json_text(text)),
        JsonSeed("oneof_number", "oneof", json_text(number)),
        JsonSeed("oneof_message", "oneof", json_text(child)),
        JsonSeed("any_packed", "any", json_text(any_parent)),
        JsonSeed("nested_maps_oneof", "nested", json_text(nested)),
        JsonSeed("nested_empty", "nested", "{}"),
        JsonSeed("timestamp", "timestamp", json_text(timestamp)),
        JsonSeed("timestamp_empty", "timestamp", "{}"),
        JsonSeed("duration", "duration", json_text(duration)),
        JsonSeed("duration_empty", "duration", "{}"),
        JsonSeed("field_mask", "fieldmask", json_text(field_mask)),
        JsonSeed("field_mask_empty", "fieldmask", "{}"),
        JsonSeed("wrappers", "wrappers", json_text(wrappers)),
        JsonSeed("wrappers_empty", "wrappers", "{}"),
        JsonSeed("struct_values", "struct", json_text(struct_values)),
        JsonSeed("struct_empty", "struct", "{}"),
    ]


def load_seed_corpus(vectors_pb2) -> list[JsonSeed]:
    """Combines reference JSON with malformed compliance-style cases."""
    seeds = shape_seeds(vectors_pb2)
    seeds.extend(
        JsonSeed(f"malformed_{name}", "maps", payload)
        for name, payload in MALFORMED_SEEDS
    )
    return seeds


def mutate_once(text: str, rng: random.Random) -> tuple[str, str]:
    """Applies one bounded JSON-text mutation."""
    data = list(text)
    operation = rng.randrange(8)

    if operation == 0 and data:
        offset = rng.randrange(len(data))
        replacement = rng.choice(JSON_ALPHABET)
        data[offset] = replacement
        return "".join(data)[:MAX_INPUT_BYTES], f"replace@{offset}:{replacement}"

    if operation == 1:
        offset = rng.randrange(len(data) + 1)
        inserted = "".join(rng.choice(JSON_ALPHABET) for _ in range(rng.randint(1, 8)))
        data[offset:offset] = list(inserted)
        return "".join(data)[:MAX_INPUT_BYTES], f"insert@{offset}:{inserted}"

    if operation == 2 and data:
        start = rng.randrange(len(data))
        count = rng.randint(1, min(8, len(data) - start))
        del data[start : start + count]
        return "".join(data), f"delete@{start}:{count}"

    if operation == 3 and data:
        length = rng.randrange(len(data))
        return "".join(data[:length]), f"truncate:{length}"

    if operation == 4:
        appended = "".join(rng.choice(JSON_ALPHABET) for _ in range(rng.randint(1, 8)))
        return (text + appended)[:MAX_INPUT_BYTES], f"append:{appended}"

    if operation == 5:
        return text.replace("{", '{"x":1,', 1)[:MAX_INPUT_BYTES], "inject_field"

    if operation == 6 and ":" in text:
        return text.replace(":", ":null", 1)[:MAX_INPUT_BYTES], "null_value"

    if data:
        start = rng.randrange(len(data))
        count = rng.randint(1, min(6, len(data) - start))
        fill = rng.choice(('"', "0", "n", "}"))
        data[start : start + count] = [fill] * count
        return "".join(data)[:MAX_INPUT_BYTES], f"fill@{start}:{count}:{fill}"

    return "{", "empty_object"


def make_cases(seed: int, count: int, corpus: list[JsonSeed]) -> list[MutationCase]:
    """Builds a deterministic case list that cycles through the whole corpus."""
    rng = random.Random(seed)
    order = list(corpus)
    rng.shuffle(order)
    cases: list[MutationCase] = []
    for index in range(count):
        base = order[index % len(order)]
        payload = base.text
        operations: list[str] = []
        for _ in range(rng.randint(1, 3)):
            payload, description = mutate_once(payload, rng)
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
    return vectors_pb2, {
        "maps": vectors_pb2.JsonStringMaps,
        "oneof": vectors_pb2.JsonOneof,
        "any": vectors_pb2.JsonAnyParent,
        "nested": vectors_pb2.Nested,
        "timestamp": vectors_pb2.JsonTimestamp,
        "duration": vectors_pb2.JsonDuration,
        "fieldmask": vectors_pb2.JsonFieldMask,
        "wrappers": vectors_pb2.JsonWrappers,
        "struct": vectors_pb2.JsonStructValues,
    }


def build_probe(output_path: Path) -> None:
    """Builds the Mojo JSON decode and re-encode probe once per fuzz run."""
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
    for kind in (
        "maps",
        "oneof",
        "any",
        "nested",
        "timestamp",
        "duration",
        "fieldmask",
        "wrappers",
        "struct",
    ):
        selected = [case for case in cases if case.kind == kind]
        if not selected:
            continue
        input_path = work_dir / f"{kind}.in"
        output_path = work_dir / f"{kind}.out"
        lines = []
        for case in selected:
            encoded = case.text.encode("utf-8")
            # Empty UTF-8 is encoded as "-". The probe must treat that as
            # empty JSON text, not as "{}".
            lines.append(encoded.hex() if encoded else "-")
        input_path.write_text("".join(line + "\n" for line in lines))
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
        rows = output_path.read_text().splitlines()
        if len(rows) != len(selected):
            raise RuntimeError(
                f"Mojo probe returned {len(rows)} {kind} rows for {len(selected)} inputs"
            )
        results.update((case.index, line) for case, line in zip(selected, rows))
    return results


def proto3_json_message_value(text: str):
    """Returns the JSON object root, or raises if the text is not an object.

    Python protobuf iterates the decoded JSON value as a mapping, so an
    empty array or empty string parses as an empty message. Proto3 JSON
    maps messages to objects, so those roots are not valid oracles.
    """
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("proto3 JSON messages must be objects")
    return value


def python_parse(message_type, text: str):
    """Returns a parsed reference message or the reference parse error."""
    message = message_type()
    try:
        json_format.Parse(text, message)
        proto3_json_message_value(text)
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
        "input_json": case.text,
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
    """Checks acceptance and semantics against Python protobuf JSON."""
    valid_agreements = 0
    malformed_agreements = 0

    for case in cases:
        expected, parse_error = python_parse(message_types[case.kind], case.text)
        result = probe_results[case.index]
        mojo_accepted = result.startswith("OK ")

        reason = ""
        if parse_error is not None:
            if mojo_accepted:
                reason = "Python protobuf rejected the JSON but protomojo accepted it"
            else:
                malformed_agreements += 1
                continue
        elif not mojo_accepted:
            reason = "Python protobuf accepted the JSON but protomojo rejected it"
        else:
            encoded_hex = result[3:]
            try:
                encoded = bytes.fromhex(encoded_hex).decode("utf-8")
            except ValueError:
                reason = "the Mojo probe returned invalid hexadecimal output"
            except UnicodeDecodeError:
                reason = "the Mojo probe returned JSON that is not UTF-8"
            else:
                actual, output_error = python_parse(
                    message_types[case.kind], encoded
                )
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
    print(
        f"PASS total agreement: {valid_agreements + malformed_agreements}/{len(cases)}"
    )
    return 0


def main() -> int:
    """Builds both oracles once, runs mutations, and reports exact counts."""
    args = parse_args()
    failure_output = args.failure_output.resolve()
    failure_output.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="protomojo-json-fuzz-") as tmp:
        work_dir = Path(tmp)
        vectors_pb2, message_types = compile_python_messages(work_dir)
        corpus = load_seed_corpus(vectors_pb2)
        cases = make_cases(args.seed, args.cases, corpus)
        print(
            f"protobuf JSON fuzz: seed={args.seed} cases={args.cases} "
            f"corpus={len(corpus)} max_input_bytes={MAX_INPUT_BYTES}"
        )
        probe = work_dir / "proto_json_probe"
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
