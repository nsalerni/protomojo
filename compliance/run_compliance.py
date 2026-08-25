#!/usr/bin/env python3
"""protomojo compliance suite.

Differentially tests the `proto` package against Python `protobuf` (the
reference implementation): seeded random messages encoded by the reference
are decoded and re-encoded by protomojo, then parsed back by the reference
and compared. Also runs Google's official protobuf conformance suite when
the runner binary is available (env CONFORMANCE_RUNNER, or
~/dev/open-source/protobuf-conformance/build/conformance_test_runner).

Rerun with: pixi run compliance   (from the package root)
Writes COMPLIANCE.md at the package root and exits non-zero on any failure.
With --json PATH, also dumps {"sections": {...}} for the umbrella suite.
"""

import argparse
import json
import math
import os
import platform
import random
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # package root
BUILD = ROOT / "build"
TOOLS = ROOT / "compliance" / "tools"
REPORT = ROOT / "COMPLIANCE.md"
CONFORMANCE_BADGE = ROOT / "conformance-badge.json"

ENUM_JSON_SEED = 20260824
REPEATED_JSON_SEED = 20260825
REPEATED_MESSAGE_JSON_SEED = 20260825
STRING_MAP_JSON_SEED = 20260825
MAP_KEY_JSON_SEED = 20260825
MESSAGE_MAP_JSON_SEED = 20260825
EXPECTED_BINARY_CONFORMANCE_SUCCESSES = 698
EXPECTED_BINARY_CONFORMANCE_SKIPS = 2081

EXPECTED_RESULT_ROWS = {
    "proto": (
        "differential decode/re-encode scalars (n=300)",
        "byte-identical re-encoding scalars (300/300)",
        "differential decode/re-encode nested (n=150)",
        "recursion depth limit agrees with protobuf (60 ok, 150 rejected)",
        "malformed-input agreement with protobuf (6/6)",
        "proto3 JSON parse differential, flat primitives (n=300)",
        "proto3 JSON print differential, flat primitives (n=300)",
        "proto3 JSON parse differential, singular nested messages (n=200)",
        "proto3 JSON print differential, singular nested messages (n=200)",
        "proto3 JSON parse differential, repeated primitives and enums "
        f"(n=200, seed={REPEATED_JSON_SEED})",
        "proto3 JSON print differential, repeated primitives and enums "
        f"(n=200, seed={REPEATED_JSON_SEED})",
        "proto3 JSON repeated accepted-edge agreement (10/10)",
        "proto3 JSON repeated rejection agreement (10/10)",
        "proto3 JSON repeated unknown enum name handling",
        "proto3 JSON parse differential, repeated messages "
        f"(n=200, seed={REPEATED_MESSAGE_JSON_SEED})",
        "proto3 JSON print differential, repeated messages "
        f"(n=200, seed={REPEATED_MESSAGE_JSON_SEED})",
        "proto3 JSON repeated message accepted-edge agreement (6/6)",
        "proto3 JSON repeated message rejection agreement (6/6)",
        "proto3 JSON repeated message unknown field handling",
        "proto3 JSON parse differential, string-key maps "
        f"(n=200, seed={STRING_MAP_JSON_SEED})",
        "proto3 JSON print differential, string-key maps "
        f"(n=200, seed={STRING_MAP_JSON_SEED})",
        "proto3 JSON string-key map accepted-edge agreement (8/8)",
        "proto3 JSON string-key map rejection agreement (8/8)",
        "proto3 JSON string-key map unknown enum name handling",
        "proto3 JSON parse differential, integer and boolean map keys "
        f"(n=200, seed={MAP_KEY_JSON_SEED})",
        "proto3 JSON print differential, integer and boolean map keys "
        f"(n=200, seed={MAP_KEY_JSON_SEED})",
        "proto3 JSON integer and boolean map key accepted-edge agreement (8/8)",
        "proto3 JSON integer and boolean map key rejection agreement (8/8)",
        "proto3 JSON parse differential, message-valued maps "
        f"(n=200, seed={MESSAGE_MAP_JSON_SEED})",
        "proto3 JSON print differential, message-valued maps "
        f"(n=200, seed={MESSAGE_MAP_JSON_SEED})",
        "proto3 JSON message-valued map accepted-edge agreement (6/6)",
        "proto3 JSON message-valued map rejection agreement (6/6)",
        "proto3 JSON message-valued map unknown field handling",
        "proto3 JSON accepted-edge agreement (20/20)",
        "proto3 JSON rejection agreement (31/31)",
        "proto3 JSON parse differential, singular enums "
        f"(n=200, seed={ENUM_JSON_SEED})",
        "proto3 JSON print differential, singular enums "
        f"(n=200, seed={ENUM_JSON_SEED})",
        "proto3 JSON enum accepted-edge agreement (7/7)",
        "proto3 JSON enum rejection agreement (6/6)",
        "proto3 JSON unknown enum name handling",
        "Google conformance, binary wire format "
        f"({EXPECTED_BINARY_CONFORMANCE_SUCCESSES} passed, 0 failed; "
        f"{EXPECTED_BINARY_CONFORMANCE_SKIPS} skipped = official JSON group, "
        "proto2, and editions, declared unsupported)",
    ),
}

ResultRows = dict[str, list[tuple[str, bool, str]]]
RESULTS: ResultRows = {}


@dataclass(frozen=True)
class ResultRegistryValidation:
    """Result-set validation shared by every generated report."""

    errors: tuple[str, ...]
    passed_count: int
    expected_count: int

    @property
    def registry_ok(self) -> bool:
        """Returns true when every declared row appears exactly once."""
        return not self.errors

    @property
    def all_ok(self) -> bool:
        """Returns true when the registry is exact and every check passed."""
        return self.registry_ok and self.passed_count == self.expected_count


def validate_result_registry(results: ResultRows) -> ResultRegistryValidation:
    """Validates section names, row names, uniqueness, and pass state."""
    errors: list[str] = []
    expected_sections = set(EXPECTED_RESULT_ROWS)
    actual_sections = set(results)
    for section in sorted(expected_sections - actual_sections):
        errors.append(f"missing section: {section}")
    for section in sorted(actual_sections - expected_sections):
        errors.append(f"unknown section: {section}")

    passed_count = 0
    for section, expected_names in EXPECTED_RESULT_ROWS.items():
        rows = results.get(section, [])
        counts = Counter(name for name, _, _ in rows)
        for name in expected_names:
            count = counts.get(name, 0)
            if count == 0:
                errors.append(f"missing row in {section}: {name}")
            elif count > 1:
                errors.append(f"duplicate row in {section}: {name}")
            else:
                row = next(row for row in rows if row[0] == name)
                if row[1]:
                    passed_count += 1
        expected_set = set(expected_names)
        for name in counts:
            if name not in expected_set:
                errors.append(f"unexpected row in {section}: {name}")

    return ResultRegistryValidation(
        errors=tuple(errors),
        passed_count=passed_count,
        expected_count=sum(len(rows) for rows in EXPECTED_RESULT_ROWS.values()),
    )


def section_result_counts(results: ResultRows, section: str) -> tuple[int, int]:
    """Counts only expected rows that appear once and pass."""
    expected_names = EXPECTED_RESULT_ROWS[section]
    outcomes: dict[str, list[bool]] = {}
    for name, ok, _ in results.get(section, []):
        outcomes.setdefault(name, []).append(bool(ok))
    passed = sum(outcomes.get(name) == [True] for name in expected_names)
    return passed, len(expected_names)


def json_values_equal(actual, expected) -> bool:
    """Compare decoded JSON values without erasing number types."""
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            json_values_equal(actual[key], expected[key]) for key in actual
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            json_values_equal(left, right)
            for left, right in zip(actual, expected)
        )
    return actual == expected


def has_exact_result_rows(rows: list[str], expected: int) -> bool:
    """Return true only when a line-oriented tool produced every row once."""
    return len(rows) == expected


def record(section: str, name: str, ok: bool, detail: str = ""):
    RESULTS.setdefault(section, []).append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'} [{section}] {name}" + ("" if ok else f"  <- {detail}"))


def run_tool(binary: str, *args, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(BUILD / binary), *map(str, args)],
        capture_output=True, text=True, timeout=timeout, cwd=ROOT,
    )


def build_tools():
    print("== building Mojo compliance tools ==")
    BUILD.mkdir(exist_ok=True)
    for src in sorted(TOOLS.glob("*.mojo")):
        out = BUILD / src.stem
        subprocess.run(
            ["mojo", "build", "-I", "src", "-I", "test",
             str(src.relative_to(ROOT)), "-o", str(out)],
            check=True, cwd=ROOT,
        )
        print(f"  built {src.stem}")


# ---------------------------------------------------------------- proto ---

def compile_test_protos(tmp: Path):
    subprocess.run(
        [sys.executable, "-m", "grpc_tools.protoc",
         f"-I{ROOT / 'test'}",
         f"--python_out={tmp}",
         str(ROOT / "test" / "vectors.proto")],
        check=True,
    )
    sys.path.insert(0, str(tmp))


def rand_scalars(pb, rng):
    s = pb.Scalars()
    if rng.random() < 0.9: s.f_int32 = rng.randint(-(2**31), 2**31 - 1)
    if rng.random() < 0.9: s.f_int64 = rng.randint(-(2**63), 2**63 - 1)
    if rng.random() < 0.9: s.f_uint32 = rng.randint(0, 2**32 - 1)
    if rng.random() < 0.9: s.f_uint64 = rng.randint(0, 2**64 - 1)
    if rng.random() < 0.9: s.f_sint32 = rng.randint(-(2**31), 2**31 - 1)
    if rng.random() < 0.9: s.f_sint64 = rng.randint(-(2**63), 2**63 - 1)
    if rng.random() < 0.5: s.f_bool = True
    if rng.random() < 0.9: s.f_fixed32 = rng.randint(0, 2**32 - 1)
    if rng.random() < 0.9: s.f_fixed64 = rng.randint(0, 2**64 - 1)
    if rng.random() < 0.9: s.f_sfixed32 = rng.randint(-(2**31), 2**31 - 1)
    if rng.random() < 0.9: s.f_sfixed64 = rng.randint(-(2**63), 2**63 - 1)
    if rng.random() < 0.9: s.f_float = rng.choice([0.5, -1.25, 3.5e10, 1e-20])
    if rng.random() < 0.9: s.f_double = rng.uniform(-1e100, 1e100)
    if rng.random() < 0.9:
        s.f_string = "".join(rng.choice("aé中🔥 xyz09") for _ in range(rng.randint(0, 40)))
    if rng.random() < 0.9:
        s.f_bytes = bytes(rng.randint(0, 255) for _ in range(rng.randint(0, 60)))
    if rng.random() < 0.5: s.f_big_field = rng.randint(-(2**31), 2**31 - 1)
    return s


def rand_json_text(rng: random.Random, maximum: int) -> str:
    alphabet = "aé中🔥 xyz09"
    return "".join(
        rng.choice(alphabet) for _ in range(rng.randint(0, maximum))
    )


def rand_json_repeated(pb, rng: random.Random):
    message = pb.JsonRepeated()

    def count() -> int:
        return rng.randint(0, 5)

    message.int32_values.extend(
        rng.randint(-(2**31), 2**31 - 1) for _ in range(count())
    )
    message.int64_values.extend(
        rng.randint(-(2**63), 2**63 - 1) for _ in range(count())
    )
    message.uint32_values.extend(
        rng.randint(0, 2**32 - 1) for _ in range(count())
    )
    message.uint64_values.extend(
        rng.randint(0, 2**64 - 1) for _ in range(count())
    )
    message.sint32_values.extend(
        rng.randint(-(2**31), 2**31 - 1) for _ in range(count())
    )
    message.sint64_values.extend(
        rng.randint(-(2**63), 2**63 - 1) for _ in range(count())
    )
    message.bool_values.extend(bool(rng.getrandbits(1)) for _ in range(count()))
    message.fixed32_values.extend(
        rng.randint(0, 2**32 - 1) for _ in range(count())
    )
    message.fixed64_values.extend(
        rng.randint(0, 2**64 - 1) for _ in range(count())
    )
    message.sfixed32_values.extend(
        rng.randint(-(2**31), 2**31 - 1) for _ in range(count())
    )
    message.sfixed64_values.extend(
        rng.randint(-(2**63), 2**63 - 1) for _ in range(count())
    )
    float_values = (0.0, 0.5, -1.25, 3.5e10, 1e-20)
    message.float_values.extend(rng.choice(float_values) for _ in range(count()))
    message.double_values.extend(
        rng.uniform(-1e100, 1e100) for _ in range(count())
    )
    message.string_values.extend(
        rand_json_text(rng, 24) for _ in range(count())
    )
    message.bytes_values.extend(
        bytes(rng.randint(0, 255) for _ in range(rng.randint(0, 24)))
        for _ in range(count())
    )
    enum_values = (0, 1, 2, -1, 123, 2147483647, -2147483648)
    message.status_values.extend(
        rng.choice(enum_values) for _ in range(count())
    )
    return message


def rand_json_repeated_messages(pb, rng: random.Random):
    message = pb.JsonRepeatedMessages()
    for index in range(rng.randint(0, 6)):
        child = message.children.add()
        if index % 3 != 0:
            child.id = rng.randint(-(2**31), 2**31 - 1)
        if index % 4 != 0:
            child.note = rand_json_text(rng, 32)
    for index in range(rng.randint(0, 6)):
        echo = message.echoes.add()
        if index % 3 != 0:
            echo.message = rand_json_text(rng, 48)
    return message


def rand_json_string_maps(pb, rng: random.Random):
    message = pb.JsonStringMaps()

    def fill(mapping, label: str, value):
        for index in range(rng.randint(0, 4)):
            key = f"{label}-{index}-{rand_json_text(rng, 12)}"
            mapping[key] = value()

    fill(
        message.int32_values,
        "i32",
        lambda: rng.randint(-(2**31), 2**31 - 1),
    )
    fill(
        message.int64_values,
        "i64",
        lambda: rng.randint(-(2**63), 2**63 - 1),
    )
    fill(
        message.uint32_values,
        "u32",
        lambda: rng.randint(0, 2**32 - 1),
    )
    fill(
        message.uint64_values,
        "u64",
        lambda: rng.randint(0, 2**64 - 1),
    )
    fill(
        message.sint32_values,
        "s32",
        lambda: rng.randint(-(2**31), 2**31 - 1),
    )
    fill(
        message.sint64_values,
        "s64",
        lambda: rng.randint(-(2**63), 2**63 - 1),
    )
    fill(message.bool_values, "bool", lambda: bool(rng.getrandbits(1)))
    fill(
        message.fixed32_values,
        "f32",
        lambda: rng.randint(0, 2**32 - 1),
    )
    fill(
        message.fixed64_values,
        "f64",
        lambda: rng.randint(0, 2**64 - 1),
    )
    fill(
        message.sfixed32_values,
        "sf32",
        lambda: rng.randint(-(2**31), 2**31 - 1),
    )
    fill(
        message.sfixed64_values,
        "sf64",
        lambda: rng.randint(-(2**63), 2**63 - 1),
    )
    fill(
        message.float_values,
        "float",
        lambda: rng.choice((0.0, 0.5, -1.25, 3.5e10, 1e-20)),
    )
    fill(
        message.double_values,
        "double",
        lambda: rng.uniform(-1e100, 1e100),
    )
    fill(message.string_values, "string", lambda: rand_json_text(rng, 24))
    fill(
        message.bytes_values,
        "bytes",
        lambda: bytes(
            rng.randint(0, 255) for _ in range(rng.randint(0, 24))
        ),
    )
    fill(
        message.status_values,
        "enum",
        lambda: rng.choice((0, 1, 2, -1, 123, 2147483647, -2147483648)),
    )
    return message


def rand_json_key_maps(pb, rng: random.Random):
    message = pb.JsonKeyMaps()

    def fill(mapping, key, value=None, maximum: int = 4):
        target = rng.randint(0, maximum)
        while len(mapping) < target:
            mapping[key()] = (
                rand_json_text(rng, 24) if value is None else value()
            )

    fill(message.int32_values, lambda: rng.randint(-(2**31), 2**31 - 1))
    fill(message.int64_values, lambda: rng.randint(-(2**63), 2**63 - 1))
    fill(message.uint32_values, lambda: rng.randint(0, 2**32 - 1))
    fill(message.uint64_values, lambda: rng.randint(0, 2**64 - 1))
    fill(message.sint32_values, lambda: rng.randint(-(2**31), 2**31 - 1))
    fill(message.sint64_values, lambda: rng.randint(-(2**63), 2**63 - 1))
    fill(
        message.bool_values,
        lambda: bool(rng.getrandbits(1)),
        maximum=2,
    )
    fill(message.fixed32_values, lambda: rng.randint(0, 2**32 - 1))
    fill(message.fixed64_values, lambda: rng.randint(0, 2**64 - 1))
    fill(message.sfixed32_values, lambda: rng.randint(-(2**31), 2**31 - 1))
    fill(message.sfixed64_values, lambda: rng.randint(-(2**63), 2**63 - 1))
    fill(
        message.int32_status_values,
        lambda: rng.randint(-(2**31), 2**31 - 1),
        lambda: rng.choice(
            (0, 1, 2, -1, 123, 2147483647, -2147483648)
        ),
    )
    return message


def rand_json_message_maps(pb, rng: random.Random):
    message = pb.JsonMessageMaps()
    for index in range(rng.randint(0, 6)):
        child = message.children[f"child-{index}-{rand_json_text(rng, 12)}"]
        if index % 3 != 0:
            child.id = rng.randint(-(2**31), 2**31 - 1)
        if index % 4 != 0:
            child.note = rand_json_text(rng, 32)
    echo_count = rng.randint(0, 6)
    while len(message.echoes) < echo_count:
        key = rng.randint(-(2**31), 2**31 - 1)
        if key not in message.echoes:
            message.echoes[key].message = rand_json_text(rng, 48)
    return message


def rand_nested(pb, rng):
    n = pb.Nested()
    if rng.random() < 0.7:
        n.inner.CopyFrom(rand_scalars(pb, rng))
    n.packed_ints.extend(rng.randint(-(2**31), 2**31 - 1) for _ in range(rng.randint(0, 20)))
    n.names.extend("n%d" % i for i in range(rng.randint(0, 6)))
    for _ in range(rng.randint(0, 3)):
        n.inners.add().CopyFrom(rand_scalars(pb, rng))
    for i in range(rng.randint(0, 5)):
        n.counts[f"k{i}"] = rng.randint(-(2**31), 2**31 - 1)
    c = rng.random()
    if c < 0.4:
        n.as_text = "chosen text"
    elif c < 0.8:
        n.as_num = rng.randint(-(2**63), 2**63 - 1)
    return n


def section_proto(tmp: Path):
    print("== proto vs Python protobuf ==")
    import vectors_pb2 as pb
    rng = random.Random(20260819)

    for kind, make, count in (("scalars", rand_scalars, 300), ("nested", rand_nested, 150)):
        msgs = [make(pb, rng) for _ in range(count)]
        if kind == "nested":
            # Pin map-entry ownership against the reference. An unknown inner
            # field makes the complete outer map field unknown. The clean
            # control contains the default value emitted by Python protobuf.
            msgs[-2] = pb.Nested.FromString(bytes.fromhex("2a050a036f6e65"))
            msgs[-1] = pb.Nested.FromString(bytes.fromhex("2a070a036f6e653000"))
        infile = tmp / f"{kind}_in.txt"
        outfile = tmp / f"{kind}_out.txt"
        infile.write_text("".join(m.SerializeToString().hex() + "\n" for m in msgs))
        r = run_tool("proto_codec", kind, infile, outfile)
        if r.returncode != 0:
            record("proto", f"differential {kind} (n={count})", False, r.stderr[:200])
            continue
        lines = outfile.read_text().splitlines()
        cls = pb.Scalars if kind == "scalars" else pb.Nested
        if len(lines) != count:
            record(
                "proto",
                f"differential decode/re-encode {kind} (n={count})",
                False,
                f"expected {count} outputs, got {len(lines)}",
            )
            continue
        bad = 0
        byte_equal = 0
        first_detail = ""
        for i, line in enumerate(lines):
            if line.startswith("ERR"):
                bad += 1
                first_detail = first_detail or f"case {i}: {line}"
                continue
            reparsed = cls.FromString(bytes.fromhex(line))
            if reparsed != msgs[i]:
                bad += 1
                first_detail = first_detail or f"case {i}: reparse mismatch"
            if line == msgs[i].SerializeToString().hex():
                byte_equal += 1
        record("proto", f"differential decode/re-encode {kind} (n={count})", bad == 0, first_detail)
        if kind == "scalars":
            record("proto", f"byte-identical re-encoding scalars ({byte_equal}/{count})",
                   byte_equal == count, f"{byte_equal}/{count}")

    # Recursion depth: both sides accept 60-deep and reject 150-deep
    # nesting (the reference's default limit is 100, ours matches).
    def tree_hex(depth: int) -> str:
        payload = b"\x10\x01"  # v = 1
        for _ in range(depth):
            payload = b"\x0a" + _varint_len(len(payload)) + payload
        return payload.hex()

    def _varint_len(n: int) -> bytes:
        out = b""
        while True:
            b = n & 0x7F
            n >>= 7
            if n:
                out += bytes([b | 0x80])
            else:
                out += bytes([b])
                return out

    infile = tmp / "tree_in.txt"; outfile = tmp / "tree_out.txt"
    infile.write_text(tree_hex(60) + "\n" + tree_hex(150) + "\n")
    run_tool("proto_codec", "tree", infile, outfile)
    tree_lines = outfile.read_text().splitlines()
    ref_ok = []
    for d in (60, 150):
        try:
            pb.Tree.FromString(bytes.fromhex(tree_hex(d)))
            ref_ok.append(True)
        except Exception:
            ref_ok.append(False)
    ours_ok = [not l.startswith("ERR") for l in tree_lines]
    record("proto", "recursion depth limit agrees with protobuf (60 ok, 150 rejected)",
           ours_ok == ref_ok and ref_ok == [True, False],
           f"ours={ours_ok} ref={ref_ok}")

    # Malformed input must be rejected, mirroring the reference behavior.
    malformed = [
        "08",
        "0880808080808080808080",
        "0a05616263",
        "1d0000",
        "0c00",
        # A legal fixed32 field followed by a tag whose field number exceeds
        # the 29-bit protobuf limit.
        "0dff808080808080ffff0142",
    ]
    infile = tmp / "bad_in.txt"; outfile = tmp / "bad_out.txt"
    infile.write_text("".join(h + "\n" for h in malformed))
    run_tool("proto_codec", "scalars", infile, outfile)
    got = outfile.read_text().splitlines()
    ref = []
    for h in malformed:
        try:
            pb.Scalars.FromString(bytes.fromhex(h))
            ref.append(True)
        except Exception:
            ref.append(False)
    agree = [g.startswith("ERR") == (not r) for g, r in zip(got, ref)]
    record("proto", f"malformed-input agreement with protobuf ({sum(agree)}/{len(agree)})",
           all(agree), str(list(zip(malformed, got, ref))) if not all(agree) else "")


def section_proto_json(tmp: Path):
    """Compare supported JSON mappings with Python protobuf."""
    import vectors_pb2 as pb
    from google.protobuf import json_format

    print("== proto3 JSON vs Python protobuf ==")
    rng = random.Random(20260823)
    messages = [rand_scalars(pb, rng) for _ in range(300)]

    # Python prints JSON, Mojo parses it, and Python checks the resulting bytes.
    infile = tmp / "json_parse_in.txt"
    outfile = tmp / "json_parse_out.txt"
    infile.write_text(
        "".join(
            json_format.MessageToJson(m, indent=None, ensure_ascii=True) + "\n"
            for m in messages
        )
    )
    result = run_tool("proto_json_codec", "parse", infile, outfile)
    parse_bad = 0
    parse_detail = ""
    if result.returncode != 0:
        parse_bad = len(messages)
        parse_detail = result.stderr[:200]
    else:
        lines = outfile.read_text().splitlines()
        if len(lines) != len(messages):
            parse_bad = len(messages)
            parse_detail = f"expected {len(messages)} rows, got {len(lines)}"
        else:
            for i, line in enumerate(lines):
                if line.startswith("ERR"):
                    parse_bad += 1
                    parse_detail = parse_detail or f"case {i}: {line}"
                    continue
                if pb.Scalars.FromString(bytes.fromhex(line)) != messages[i]:
                    parse_bad += 1
                    parse_detail = parse_detail or f"case {i}: semantic mismatch"
    record(
        "proto",
        "proto3 JSON parse differential, flat primitives (n=300)",
        parse_bad == 0,
        parse_detail,
    )

    # Python provides binary data, Mojo prints JSON, and Python parses it.
    infile = tmp / "json_print_in.txt"
    outfile = tmp / "json_print_out.txt"
    infile.write_text("".join(m.SerializeToString().hex() + "\n" for m in messages))
    result = run_tool("proto_json_codec", "print", infile, outfile)
    print_bad = 0
    print_detail = ""
    if result.returncode != 0:
        print_bad = len(messages)
        print_detail = result.stderr[:200]
    else:
        lines = outfile.read_text().splitlines()
        if len(lines) != len(messages):
            print_bad = len(messages)
            print_detail = f"expected {len(messages)} rows, got {len(lines)}"
        else:
            for i, line in enumerate(lines):
                case_errors = []
                try:
                    actual_json = json.loads(line)
                    reference_json = json.loads(
                        json_format.MessageToJson(messages[i])
                    )
                    if not json_values_equal(actual_json, reference_json):
                        case_errors.append(
                            f"JSON value mismatch: {actual_json!r} != "
                            f"{reference_json!r}"
                        )
                except Exception as exc:
                    case_errors.append(f"invalid JSON output: {exc}")
                try:
                    reparsed = json_format.Parse(line, pb.Scalars())
                except Exception as exc:
                    case_errors.append(f"protobuf parse failed: {exc}")
                else:
                    if reparsed != messages[i]:
                        case_errors.append("protobuf semantic mismatch")
                if case_errors:
                    print_bad += 1
                    print_detail = print_detail or (
                        f"case {i}: " + "; ".join(case_errors)
                    )
    record(
        "proto",
        "proto3 JSON print differential, flat primitives (n=300)",
        print_bad == 0,
        print_detail,
    )

    nested_messages = []
    for index in range(200):
        message = pb.JsonParent()
        if index % 5 != 0:
            message.child.id = rng.randint(-2147483648, 2147483647)
            if index % 7 != 0:
                message.child.note = rand_json_text(rng, 32)
        if index % 3 != 0:
            message.echo.message = rand_json_text(rng, 48)
        nested_messages.append(message)

    infile = tmp / "json_nested_parse_in.txt"
    outfile = tmp / "json_nested_parse_out.txt"
    infile.write_text(
        "".join(
            json_format.MessageToJson(message, indent=None, ensure_ascii=True)
            + "\n"
            for message in nested_messages
        )
    )
    result = run_tool("proto_json_codec", "parse-nested", infile, outfile)
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    nested_parse_ok = has_exact_result_rows(rows, len(nested_messages))
    nested_parse_detail = ""
    if nested_parse_ok:
        for index, row in enumerate(rows):
            if row.startswith("ERR") or (
                pb.JsonParent.FromString(bytes.fromhex(row))
                != nested_messages[index]
            ):
                nested_parse_ok = False
                nested_parse_detail = f"case {index}: {row}"
                break
    else:
        nested_parse_detail = (
            f"expected {len(nested_messages)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON parse differential, singular nested messages (n=200)",
        nested_parse_ok,
        nested_parse_detail,
    )

    infile = tmp / "json_nested_print_in.txt"
    outfile = tmp / "json_nested_print_out.txt"
    infile.write_text(
        "".join(
            (message.SerializeToString().hex() or "-") + "\n"
            for message in nested_messages
        )
    )
    result = run_tool("proto_json_codec", "print-nested", infile, outfile)
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    nested_print_ok = has_exact_result_rows(rows, len(nested_messages))
    nested_print_detail = ""
    if nested_print_ok:
        for index, row in enumerate(rows):
            try:
                actual = json.loads(row)
                expected = json.loads(
                    json_format.MessageToJson(nested_messages[index])
                )
                reparsed = json_format.Parse(row, pb.JsonParent())
            except Exception as error:
                nested_print_ok = False
                nested_print_detail = f"case {index}: {error}"
                break
            if (
                not json_values_equal(actual, expected)
                or reparsed != nested_messages[index]
            ):
                nested_print_ok = False
                nested_print_detail = f"case {index}: {actual!r} != {expected!r}"
                break
    else:
        nested_print_detail = (
            f"expected {len(nested_messages)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON print differential, singular nested messages (n=200)",
        nested_print_ok,
        nested_print_detail,
    )

    repeated_rng = random.Random(REPEATED_JSON_SEED)
    repeated_messages = [
        rand_json_repeated(pb, repeated_rng) for _ in range(200)
    ]
    infile = tmp / "json_repeated_parse_in.txt"
    outfile = tmp / "json_repeated_parse_out.txt"
    infile.write_text(
        "".join(
            json_format.MessageToJson(message, indent=None, ensure_ascii=True)
            + "\n"
            for message in repeated_messages
        )
    )
    result = run_tool("proto_json_codec", "parse-repeated", infile, outfile)
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    repeated_parse_ok = has_exact_result_rows(rows, len(repeated_messages))
    repeated_parse_detail = ""
    if repeated_parse_ok:
        for index, row in enumerate(rows):
            if row.startswith("ERR") or (
                pb.JsonRepeated.FromString(bytes.fromhex(row))
                != repeated_messages[index]
            ):
                repeated_parse_ok = False
                repeated_parse_detail = f"case {index}: {row}"
                break
    else:
        repeated_parse_detail = (
            f"expected {len(repeated_messages)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON parse differential, repeated primitives and enums "
        f"(n=200, seed={REPEATED_JSON_SEED})",
        repeated_parse_ok,
        repeated_parse_detail,
    )

    infile = tmp / "json_repeated_print_in.txt"
    outfile = tmp / "json_repeated_print_out.txt"
    infile.write_text(
        "".join(
            (message.SerializeToString().hex() or "-") + "\n"
            for message in repeated_messages
        )
    )
    result = run_tool("proto_json_codec", "print-repeated", infile, outfile)
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    repeated_print_ok = has_exact_result_rows(rows, len(repeated_messages))
    repeated_print_detail = ""
    if repeated_print_ok:
        for index, row in enumerate(rows):
            try:
                actual = json.loads(row)
                expected = json.loads(
                    json_format.MessageToJson(repeated_messages[index])
                )
                reparsed = json_format.Parse(row, pb.JsonRepeated())
            except Exception as error:
                repeated_print_ok = False
                repeated_print_detail = f"case {index}: {error}"
                break
            if (
                not json_values_equal(actual, expected)
                or reparsed != repeated_messages[index]
            ):
                repeated_print_ok = False
                repeated_print_detail = (
                    f"case {index}: {actual!r} != {expected!r}"
                )
                break
    else:
        repeated_print_detail = (
            f"expected {len(repeated_messages)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON print differential, repeated primitives and enums "
        f"(n=200, seed={REPEATED_JSON_SEED})",
        repeated_print_ok,
        repeated_print_detail,
    )

    repeated_edges = [
        "{}",
        '{"int32Values":[]}',
        '{"int32Values":null}',
        '{"int32Values":[-2147483648,2147483647]}',
        '{"int64Values":["-9223372036854775808","9223372036854775807"]}',
        '{"uint64Values":["0","18446744073709551615"]}',
        '{"floatValues":["NaN","Infinity","-Infinity",1.25]}',
        '{"stringValues":["","é","中🔥"]}',
        '{"bytesValues":["","AQI=","-_"]}',
        '{"statusValues":["STATUS_ACTIVE","STATUS_ENABLED",-1,123]}',
    ]
    infile = tmp / "json_repeated_edges_in.txt"
    outfile = tmp / "json_repeated_edges_out.txt"
    infile.write_text("".join(case + "\n" for case in repeated_edges))
    result = run_tool("proto_json_codec", "parse-repeated", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    repeated_edges_ok = has_exact_result_rows(mojo_rows, len(repeated_edges))
    repeated_edges_detail = ""
    if repeated_edges_ok:
        for index, case in enumerate(repeated_edges):
            expected = json_format.Parse(case, pb.JsonRepeated())
            row = mojo_rows[index]
            if row.startswith("ERR"):
                repeated_edges_ok = False
                repeated_edges_detail = f"case {index}: {case} -> {row}"
                break
            actual = pb.JsonRepeated.FromString(bytes.fromhex(row))
            if case.find('"NaN"') >= 0:
                actual_values = list(actual.float_values)
                expected_values = list(expected.float_values)
                if not (
                    len(actual_values) == len(expected_values)
                    and all(
                        math.isnan(left) and math.isnan(right)
                        if math.isnan(left) or math.isnan(right)
                        else left == right
                        for left, right in zip(actual_values, expected_values)
                    )
                ):
                    repeated_edges_ok = False
                    repeated_edges_detail = f"case {index}: float mismatch"
                    break
                actual.ClearField("float_values")
                expected.ClearField("float_values")
            if actual != expected:
                repeated_edges_ok = False
                repeated_edges_detail = f"case {index}: semantic mismatch"
                break
    else:
        repeated_edges_detail = (
            f"expected {len(repeated_edges)} rows, got {len(mojo_rows)}"
        )
    record(
        "proto",
        "proto3 JSON repeated accepted-edge agreement "
        f"({len(repeated_edges) if repeated_edges_ok else 0}/"
        f"{len(repeated_edges)})",
        repeated_edges_ok,
        repeated_edges_detail,
    )

    repeated_rejected = [
        '{"int32Values":1}',
        '{"int32Values":[null]}',
        '{"int32Values":[2147483648]}',
        '{"boolValues":[1]}',
        '{"bytesValues":["A!"]}',
        '{"statusValues":["STATUS_MISSING"]}',
        '{"stringValues":[1]}',
        '{"int32Values":[1,]}',
        '{"int32Values":[{}]}',
        '{"int32Values":[1],"int32Values":[2]}',
    ]
    infile = tmp / "json_repeated_reject_in.txt"
    outfile = tmp / "json_repeated_reject_out.txt"
    infile.write_text("".join(case + "\n" for case in repeated_rejected))
    result = run_tool("proto_json_codec", "parse-repeated", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    repeated_reject_ok = has_exact_result_rows(
        mojo_rows, len(repeated_rejected)
    )
    if repeated_reject_ok:
        for index, case in enumerate(repeated_rejected):
            try:
                json_format.Parse(case, pb.JsonRepeated())
                python_rejects = False
            except Exception:
                python_rejects = True
            if not mojo_rows[index].startswith("ERR") or not python_rejects:
                repeated_reject_ok = False
                break
    repeated_reject_detail = "" if repeated_reject_ok else str(mojo_rows)
    record(
        "proto",
        "proto3 JSON repeated rejection agreement "
        f"({len(repeated_rejected) if repeated_reject_ok else 0}/"
        f"{len(repeated_rejected)})",
        repeated_reject_ok,
        repeated_reject_detail,
    )

    repeated_unknown_enum = (
        '{"statusValues":["STATUS_ACTIVE","STATUS_MISSING",123]}'
    )
    infile = tmp / "json_repeated_enum_ignore_in.txt"
    outfile = tmp / "json_repeated_enum_ignore_out.txt"
    infile.write_text(repeated_unknown_enum + "\n")
    result = run_tool(
        "proto_json_codec",
        "parse-repeated-ignore-unknown",
        infile,
        outfile,
    )
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    expected = json_format.Parse(
        repeated_unknown_enum,
        pb.JsonRepeated(),
        ignore_unknown_fields=True,
    )
    repeated_unknown_enum_ok = (
        has_exact_result_rows(mojo_rows, 1)
        and not mojo_rows[0].startswith("ERR")
        and pb.JsonRepeated.FromString(bytes.fromhex(mojo_rows[0])) == expected
    )
    record(
        "proto",
        "proto3 JSON repeated unknown enum name handling",
        repeated_unknown_enum_ok,
        "" if repeated_unknown_enum_ok else str(mojo_rows),
    )

    repeated_message_rng = random.Random(REPEATED_MESSAGE_JSON_SEED)
    repeated_message_values = [
        rand_json_repeated_messages(pb, repeated_message_rng)
        for _ in range(200)
    ]
    infile = tmp / "json_repeated_message_parse_in.txt"
    outfile = tmp / "json_repeated_message_parse_out.txt"
    infile.write_text(
        "".join(
            json_format.MessageToJson(message, indent=None, ensure_ascii=True)
            + "\n"
            for message in repeated_message_values
        )
    )
    result = run_tool(
        "proto_json_codec", "parse-repeated-messages", infile, outfile
    )
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    repeated_message_parse_ok = has_exact_result_rows(
        rows, len(repeated_message_values)
    )
    repeated_message_parse_detail = ""
    if repeated_message_parse_ok:
        for index, row in enumerate(rows):
            if row.startswith("ERR") or (
                pb.JsonRepeatedMessages.FromString(bytes.fromhex(row))
                != repeated_message_values[index]
            ):
                repeated_message_parse_ok = False
                repeated_message_parse_detail = f"case {index}: {row}"
                break
    else:
        repeated_message_parse_detail = (
            f"expected {len(repeated_message_values)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON parse differential, repeated messages "
        f"(n=200, seed={REPEATED_MESSAGE_JSON_SEED})",
        repeated_message_parse_ok,
        repeated_message_parse_detail,
    )

    infile = tmp / "json_repeated_message_print_in.txt"
    outfile = tmp / "json_repeated_message_print_out.txt"
    infile.write_text(
        "".join(
            (message.SerializeToString().hex() or "-") + "\n"
            for message in repeated_message_values
        )
    )
    result = run_tool(
        "proto_json_codec", "print-repeated-messages", infile, outfile
    )
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    repeated_message_print_ok = has_exact_result_rows(
        rows, len(repeated_message_values)
    )
    repeated_message_print_detail = ""
    if repeated_message_print_ok:
        for index, row in enumerate(rows):
            try:
                actual = json.loads(row)
                expected = json.loads(
                    json_format.MessageToJson(repeated_message_values[index])
                )
                reparsed = json_format.Parse(row, pb.JsonRepeatedMessages())
            except Exception as error:
                repeated_message_print_ok = False
                repeated_message_print_detail = f"case {index}: {error}"
                break
            if (
                not json_values_equal(actual, expected)
                or reparsed != repeated_message_values[index]
            ):
                repeated_message_print_ok = False
                repeated_message_print_detail = (
                    f"case {index}: {actual!r} != {expected!r}"
                )
                break
    else:
        repeated_message_print_detail = (
            f"expected {len(repeated_message_values)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON print differential, repeated messages "
        f"(n=200, seed={REPEATED_MESSAGE_JSON_SEED})",
        repeated_message_print_ok,
        repeated_message_print_detail,
    )

    repeated_message_edges = [
        "{}",
        '{"children":[]}',
        '{"children":null}',
        '{"children":[{}, {"id":7,"note":"ok"}]}',
        '{"echoes":[{"message":"é 中🔥"}]}',
        '{"children":[{"id":-2147483648}],"echoes":[{},{}]}',
    ]
    infile = tmp / "json_repeated_message_edges_in.txt"
    outfile = tmp / "json_repeated_message_edges_out.txt"
    infile.write_text("".join(case + "\n" for case in repeated_message_edges))
    result = run_tool(
        "proto_json_codec", "parse-repeated-messages", infile, outfile
    )
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    repeated_message_edges_ok = has_exact_result_rows(
        mojo_rows, len(repeated_message_edges)
    )
    repeated_message_edges_detail = ""
    if repeated_message_edges_ok:
        for index, case in enumerate(repeated_message_edges):
            expected = json_format.Parse(case, pb.JsonRepeatedMessages())
            row = mojo_rows[index]
            if row.startswith("ERR") or (
                pb.JsonRepeatedMessages.FromString(bytes.fromhex(row))
                != expected
            ):
                repeated_message_edges_ok = False
                repeated_message_edges_detail = f"case {index}: {case} -> {row}"
                break
    else:
        repeated_message_edges_detail = (
            f"expected {len(repeated_message_edges)} rows, got {len(mojo_rows)}"
        )
    record(
        "proto",
        "proto3 JSON repeated message accepted-edge agreement "
        f"({len(repeated_message_edges) if repeated_message_edges_ok else 0}/"
        f"{len(repeated_message_edges)})",
        repeated_message_edges_ok,
        repeated_message_edges_detail,
    )

    repeated_message_rejected = [
        '{"children":{}}',
        '{"children":[null]}',
        '{"children":[1]}',
        '{"children":[{"unknown":1}]}',
        '{"children":[{"id":1,"id":2}]}',
        '{"children":[{},]}',
    ]
    infile = tmp / "json_repeated_message_reject_in.txt"
    outfile = tmp / "json_repeated_message_reject_out.txt"
    infile.write_text(
        "".join(case + "\n" for case in repeated_message_rejected)
    )
    result = run_tool(
        "proto_json_codec", "parse-repeated-messages", infile, outfile
    )
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    repeated_message_reject_ok = has_exact_result_rows(
        mojo_rows, len(repeated_message_rejected)
    )
    if repeated_message_reject_ok:
        for index, case in enumerate(repeated_message_rejected):
            try:
                json_format.Parse(case, pb.JsonRepeatedMessages())
                python_rejects = False
            except Exception:
                python_rejects = True
            if not mojo_rows[index].startswith("ERR") or not python_rejects:
                repeated_message_reject_ok = False
                break
    repeated_message_reject_detail = (
        "" if repeated_message_reject_ok else str(mojo_rows)
    )
    record(
        "proto",
        "proto3 JSON repeated message rejection agreement "
        f"({len(repeated_message_rejected) if repeated_message_reject_ok else 0}/"
        f"{len(repeated_message_rejected)})",
        repeated_message_reject_ok,
        repeated_message_reject_detail,
    )

    repeated_message_unknown = (
        '{"children":[{"id":1,"unknown":{"nested":true}}]}'
    )
    infile = tmp / "json_repeated_message_ignore_in.txt"
    outfile = tmp / "json_repeated_message_ignore_out.txt"
    infile.write_text(repeated_message_unknown + "\n")
    result = run_tool(
        "proto_json_codec",
        "parse-repeated-messages-ignore-unknown",
        infile,
        outfile,
    )
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    expected = json_format.Parse(
        repeated_message_unknown,
        pb.JsonRepeatedMessages(),
        ignore_unknown_fields=True,
    )
    repeated_message_unknown_ok = (
        has_exact_result_rows(mojo_rows, 1)
        and not mojo_rows[0].startswith("ERR")
        and pb.JsonRepeatedMessages.FromString(bytes.fromhex(mojo_rows[0]))
        == expected
    )
    record(
        "proto",
        "proto3 JSON repeated message unknown field handling",
        repeated_message_unknown_ok,
        "" if repeated_message_unknown_ok else str(mojo_rows),
    )

    string_map_rng = random.Random(STRING_MAP_JSON_SEED)
    string_map_values = [
        rand_json_string_maps(pb, string_map_rng) for _ in range(200)
    ]
    infile = tmp / "json_string_map_parse_in.txt"
    outfile = tmp / "json_string_map_parse_out.txt"
    infile.write_text(
        "".join(
            json_format.MessageToJson(message, indent=None, ensure_ascii=True)
            + "\n"
            for message in string_map_values
        )
    )
    result = run_tool("proto_json_codec", "parse-string-maps", infile, outfile)
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    string_map_parse_ok = has_exact_result_rows(rows, len(string_map_values))
    string_map_parse_detail = ""
    if string_map_parse_ok:
        for index, row in enumerate(rows):
            if row.startswith("ERR") or (
                pb.JsonStringMaps.FromString(bytes.fromhex(row))
                != string_map_values[index]
            ):
                string_map_parse_ok = False
                string_map_parse_detail = f"case {index}: {row}"
                break
    else:
        string_map_parse_detail = (
            f"expected {len(string_map_values)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON parse differential, string-key maps "
        f"(n=200, seed={STRING_MAP_JSON_SEED})",
        string_map_parse_ok,
        string_map_parse_detail,
    )

    infile = tmp / "json_string_map_print_in.txt"
    outfile = tmp / "json_string_map_print_out.txt"
    infile.write_text(
        "".join(
            (message.SerializeToString().hex() or "-") + "\n"
            for message in string_map_values
        )
    )
    result = run_tool("proto_json_codec", "print-string-maps", infile, outfile)
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    string_map_print_ok = has_exact_result_rows(rows, len(string_map_values))
    string_map_print_detail = ""
    if string_map_print_ok:
        for index, row in enumerate(rows):
            try:
                actual = json.loads(row)
                expected = json.loads(
                    json_format.MessageToJson(string_map_values[index])
                )
                reparsed = json_format.Parse(row, pb.JsonStringMaps())
            except Exception as error:
                string_map_print_ok = False
                string_map_print_detail = f"case {index}: {error}"
                break
            if (
                not json_values_equal(actual, expected)
                or reparsed != string_map_values[index]
            ):
                string_map_print_ok = False
                string_map_print_detail = (
                    f"case {index}: {actual!r} != {expected!r}"
                )
                break
    else:
        string_map_print_detail = (
            f"expected {len(string_map_values)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON print differential, string-key maps "
        f"(n=200, seed={STRING_MAP_JSON_SEED})",
        string_map_print_ok,
        string_map_print_detail,
    )

    string_map_edges = [
        "{}",
        '{"int32Values":{}}',
        '{"int32Values":null}',
        '{"int32Values":{"a\\\"b":-2147483648}}',
        '{"int64Values":{"max":"9223372036854775807"}}',
        '{"uint64Values":{"max":"18446744073709551615"}}',
        '{"bytesValues":{"key":"-_"}}',
        '{"statusValues":{"first":"STATUS_ENABLED","unknown":123}}',
    ]
    infile = tmp / "json_string_map_edges_in.txt"
    outfile = tmp / "json_string_map_edges_out.txt"
    infile.write_text("".join(case + "\n" for case in string_map_edges))
    result = run_tool("proto_json_codec", "parse-string-maps", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    string_map_edges_ok = has_exact_result_rows(mojo_rows, len(string_map_edges))
    string_map_edges_detail = ""
    if string_map_edges_ok:
        for index, case in enumerate(string_map_edges):
            expected = json_format.Parse(case, pb.JsonStringMaps())
            row = mojo_rows[index]
            if row.startswith("ERR") or (
                pb.JsonStringMaps.FromString(bytes.fromhex(row)) != expected
            ):
                string_map_edges_ok = False
                string_map_edges_detail = f"case {index}: {case} -> {row}"
                break
    else:
        string_map_edges_detail = (
            f"expected {len(string_map_edges)} rows, got {len(mojo_rows)}"
        )
    record(
        "proto",
        "proto3 JSON string-key map accepted-edge agreement "
        f"({len(string_map_edges) if string_map_edges_ok else 0}/"
        f"{len(string_map_edges)})",
        string_map_edges_ok,
        string_map_edges_detail,
    )

    string_map_rejected = [
        '{"int32Values":[]}',
        '{"int32Values":{"bad":null}}',
        '{"int32Values":{"same":1,"same":2}}',
        '{"int32Values":{"bad":1,}}',
        '{"int32Values":{"bad":"text"}}',
        '{"statusValues":{"bad":"UNKNOWN"}}',
        '{"int32Values":1}',
        '{"int32Values":{"bad":{}}}',
    ]
    infile = tmp / "json_string_map_reject_in.txt"
    outfile = tmp / "json_string_map_reject_out.txt"
    infile.write_text("".join(case + "\n" for case in string_map_rejected))
    result = run_tool("proto_json_codec", "parse-string-maps", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    string_map_reject_ok = has_exact_result_rows(
        mojo_rows, len(string_map_rejected)
    )
    if string_map_reject_ok:
        for index, case in enumerate(string_map_rejected):
            try:
                json_format.Parse(case, pb.JsonStringMaps())
                python_rejects = False
            except Exception:
                python_rejects = True
            if not mojo_rows[index].startswith("ERR") or not python_rejects:
                string_map_reject_ok = False
                break
    string_map_reject_detail = (
        "" if string_map_reject_ok else str(mojo_rows)
    )
    record(
        "proto",
        "proto3 JSON string-key map rejection agreement "
        f"({len(string_map_rejected) if string_map_reject_ok else 0}/"
        f"{len(string_map_rejected)})",
        string_map_reject_ok,
        string_map_reject_detail,
    )

    string_map_unknown = (
        '{"statusValues":{"known":"STATUS_ACTIVE","bad":"UNKNOWN"}}'
    )
    infile = tmp / "json_string_map_ignore_in.txt"
    outfile = tmp / "json_string_map_ignore_out.txt"
    infile.write_text(string_map_unknown + "\n")
    result = run_tool(
        "proto_json_codec",
        "parse-string-maps-ignore-unknown",
        infile,
        outfile,
    )
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    expected = json_format.Parse(
        string_map_unknown,
        pb.JsonStringMaps(),
        ignore_unknown_fields=True,
    )
    string_map_unknown_ok = (
        has_exact_result_rows(mojo_rows, 1)
        and not mojo_rows[0].startswith("ERR")
        and pb.JsonStringMaps.FromString(bytes.fromhex(mojo_rows[0]))
        == expected
    )
    record(
        "proto",
        "proto3 JSON string-key map unknown enum name handling",
        string_map_unknown_ok,
        "" if string_map_unknown_ok else str(mojo_rows),
    )

    map_key_rng = random.Random(MAP_KEY_JSON_SEED)
    map_key_values = [rand_json_key_maps(pb, map_key_rng) for _ in range(200)]
    infile = tmp / "json_map_key_parse_in.txt"
    outfile = tmp / "json_map_key_parse_out.txt"
    infile.write_text(
        "".join(
            json_format.MessageToJson(message, indent=None, ensure_ascii=True)
            + "\n"
            for message in map_key_values
        )
    )
    result = run_tool("proto_json_codec", "parse-key-maps", infile, outfile)
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    map_key_parse_ok = has_exact_result_rows(rows, len(map_key_values))
    map_key_parse_detail = ""
    if map_key_parse_ok:
        for index, row in enumerate(rows):
            if row.startswith("ERR") or (
                pb.JsonKeyMaps.FromString(bytes.fromhex(row))
                != map_key_values[index]
            ):
                map_key_parse_ok = False
                map_key_parse_detail = f"case {index}: {row}"
                break
    else:
        map_key_parse_detail = (
            f"expected {len(map_key_values)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON parse differential, integer and boolean map keys "
        f"(n=200, seed={MAP_KEY_JSON_SEED})",
        map_key_parse_ok,
        map_key_parse_detail,
    )

    infile = tmp / "json_map_key_print_in.txt"
    outfile = tmp / "json_map_key_print_out.txt"
    infile.write_text(
        "".join(
            (message.SerializeToString().hex() or "-") + "\n"
            for message in map_key_values
        )
    )
    result = run_tool("proto_json_codec", "print-key-maps", infile, outfile)
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    map_key_print_ok = has_exact_result_rows(rows, len(map_key_values))
    map_key_print_detail = ""
    if map_key_print_ok:
        for index, row in enumerate(rows):
            try:
                actual = json.loads(row)
                expected = json.loads(
                    json_format.MessageToJson(map_key_values[index])
                )
                reparsed = json_format.Parse(row, pb.JsonKeyMaps())
            except Exception as error:
                map_key_print_ok = False
                map_key_print_detail = f"case {index}: {error}"
                break
            if (
                not json_values_equal(actual, expected)
                or reparsed != map_key_values[index]
            ):
                map_key_print_ok = False
                map_key_print_detail = (
                    f"case {index}: {actual!r} != {expected!r}"
                )
                break
    else:
        map_key_print_detail = (
            f"expected {len(map_key_values)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON print differential, integer and boolean map keys "
        f"(n=200, seed={MAP_KEY_JSON_SEED})",
        map_key_print_ok,
        map_key_print_detail,
    )

    map_key_edges = [
        "{}",
        '{"int32Values":{"-2147483648":"min"}}',
        '{"uint32Values":{"4294967295":"max"}}',
        '{"int64Values":{"-9223372036854775808":"min"}}',
        '{"uint64Values":{"18446744073709551615":"max"}}',
        '{"boolValues":{"true":"yes","false":"no"}}',
        '{"int32Values":{"\\u0031":"escaped"}}',
        '{"boolValues":{"tr\\u0075e":"escaped"}}',
    ]
    infile = tmp / "json_map_key_edges_in.txt"
    outfile = tmp / "json_map_key_edges_out.txt"
    infile.write_text("".join(case + "\n" for case in map_key_edges))
    result = run_tool("proto_json_codec", "parse-key-maps", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    map_key_edges_ok = has_exact_result_rows(mojo_rows, len(map_key_edges))
    map_key_edges_detail = ""
    if map_key_edges_ok:
        for index, case in enumerate(map_key_edges):
            expected = json_format.Parse(case, pb.JsonKeyMaps())
            row = mojo_rows[index]
            if row.startswith("ERR") or (
                pb.JsonKeyMaps.FromString(bytes.fromhex(row)) != expected
            ):
                map_key_edges_ok = False
                map_key_edges_detail = f"case {index}: {case} -> {row}"
                break
    else:
        map_key_edges_detail = (
            f"expected {len(map_key_edges)} rows, got {len(mojo_rows)}"
        )
    record(
        "proto",
        "proto3 JSON integer and boolean map key accepted-edge agreement "
        f"({len(map_key_edges) if map_key_edges_ok else 0}/"
        f"{len(map_key_edges)})",
        map_key_edges_ok,
        map_key_edges_detail,
    )

    map_key_rejected = [
        '{"int32Values":{1:"bad"}}',
        '{"int32Values":{"2147483648":"bad"}}',
        '{"uint32Values":{"-1":"bad"}}',
        '{"int64Values":{"9223372036854775808":"bad"}}',
        '{"uint64Values":{"18446744073709551616":"bad"}}',
        '{"boolValues":{"True":"bad"}}',
        '{"boolValues":{"1":"bad"}}',
        '{"int32Values":{"nope":"bad"}}',
    ]
    infile = tmp / "json_map_key_reject_in.txt"
    outfile = tmp / "json_map_key_reject_out.txt"
    infile.write_text("".join(case + "\n" for case in map_key_rejected))
    result = run_tool("proto_json_codec", "parse-key-maps", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    map_key_reject_ok = has_exact_result_rows(mojo_rows, len(map_key_rejected))
    if map_key_reject_ok:
        for index, case in enumerate(map_key_rejected):
            try:
                json_format.Parse(case, pb.JsonKeyMaps())
                python_rejects = False
            except Exception:
                python_rejects = True
            if not mojo_rows[index].startswith("ERR") or not python_rejects:
                map_key_reject_ok = False
                break
    map_key_reject_detail = "" if map_key_reject_ok else str(mojo_rows)
    record(
        "proto",
        "proto3 JSON integer and boolean map key rejection agreement "
        f"({len(map_key_rejected) if map_key_reject_ok else 0}/"
        f"{len(map_key_rejected)})",
        map_key_reject_ok,
        map_key_reject_detail,
    )

    message_map_rng = random.Random(MESSAGE_MAP_JSON_SEED)
    message_map_values = [
        rand_json_message_maps(pb, message_map_rng) for _ in range(200)
    ]
    infile = tmp / "json_message_map_parse_in.txt"
    outfile = tmp / "json_message_map_parse_out.txt"
    infile.write_text(
        "".join(
            json_format.MessageToJson(message, indent=None, ensure_ascii=True)
            + "\n"
            for message in message_map_values
        )
    )
    result = run_tool("proto_json_codec", "parse-message-maps", infile, outfile)
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    message_map_parse_ok = has_exact_result_rows(rows, len(message_map_values))
    message_map_parse_detail = ""
    if message_map_parse_ok:
        for index, row in enumerate(rows):
            if row.startswith("ERR") or (
                pb.JsonMessageMaps.FromString(bytes.fromhex(row))
                != message_map_values[index]
            ):
                message_map_parse_ok = False
                message_map_parse_detail = f"case {index}: {row}"
                break
    else:
        message_map_parse_detail = (
            f"expected {len(message_map_values)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON parse differential, message-valued maps "
        f"(n=200, seed={MESSAGE_MAP_JSON_SEED})",
        message_map_parse_ok,
        message_map_parse_detail,
    )

    infile = tmp / "json_message_map_print_in.txt"
    outfile = tmp / "json_message_map_print_out.txt"
    infile.write_text(
        "".join(
            (message.SerializeToString().hex() or "-") + "\n"
            for message in message_map_values
        )
    )
    result = run_tool("proto_json_codec", "print-message-maps", infile, outfile)
    rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    message_map_print_ok = has_exact_result_rows(rows, len(message_map_values))
    message_map_print_detail = ""
    if message_map_print_ok:
        for index, row in enumerate(rows):
            try:
                actual = json.loads(row)
                expected = json.loads(
                    json_format.MessageToJson(message_map_values[index])
                )
                reparsed = json_format.Parse(row, pb.JsonMessageMaps())
            except Exception as error:
                message_map_print_ok = False
                message_map_print_detail = f"case {index}: {error}"
                break
            if (
                not json_values_equal(actual, expected)
                or reparsed != message_map_values[index]
            ):
                message_map_print_ok = False
                message_map_print_detail = (
                    f"case {index}: {actual!r} != {expected!r}"
                )
                break
    else:
        message_map_print_detail = (
            f"expected {len(message_map_values)} rows, got {len(rows)}; "
            f"rc={result.returncode} err={result.stderr[:160]!r}"
        )
    record(
        "proto",
        "proto3 JSON print differential, message-valued maps "
        f"(n=200, seed={MESSAGE_MAP_JSON_SEED})",
        message_map_print_ok,
        message_map_print_detail,
    )

    message_map_edges = [
        "{}",
        '{"children":{}}',
        '{"children":null}',
        '{"children":{"empty":{}}}',
        '{"children":{"full":{"id":7,"note":"ok"}}}',
        '{"echoes":{"-2147483648":{"message":"edge"}}}',
    ]
    infile = tmp / "json_message_map_edges_in.txt"
    outfile = tmp / "json_message_map_edges_out.txt"
    infile.write_text("".join(case + "\n" for case in message_map_edges))
    result = run_tool("proto_json_codec", "parse-message-maps", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    message_map_edges_ok = has_exact_result_rows(
        mojo_rows, len(message_map_edges)
    )
    message_map_edges_detail = ""
    if message_map_edges_ok:
        for index, case in enumerate(message_map_edges):
            expected = json_format.Parse(case, pb.JsonMessageMaps())
            row = mojo_rows[index]
            if row.startswith("ERR") or (
                pb.JsonMessageMaps.FromString(bytes.fromhex(row)) != expected
            ):
                message_map_edges_ok = False
                message_map_edges_detail = f"case {index}: {case} -> {row}"
                break
    else:
        message_map_edges_detail = (
            f"expected {len(message_map_edges)} rows, got {len(mojo_rows)}"
        )
    record(
        "proto",
        "proto3 JSON message-valued map accepted-edge agreement "
        f"({len(message_map_edges) if message_map_edges_ok else 0}/"
        f"{len(message_map_edges)})",
        message_map_edges_ok,
        message_map_edges_detail,
    )

    message_map_rejected = [
        '{"children":{"bad":null}}',
        '{"children":{"bad":1}}',
        '{"children":{"bad":"text"}}',
        '{"children":{"bad":{"unknown":1}}}',
        '{"children":{"bad":{"id":1,"id":2}}}',
        '{"children":{"bad":{},}}',
    ]
    infile = tmp / "json_message_map_reject_in.txt"
    outfile = tmp / "json_message_map_reject_out.txt"
    infile.write_text("".join(case + "\n" for case in message_map_rejected))
    result = run_tool("proto_json_codec", "parse-message-maps", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    message_map_reject_ok = has_exact_result_rows(
        mojo_rows, len(message_map_rejected)
    )
    if message_map_reject_ok:
        for index, case in enumerate(message_map_rejected):
            try:
                json_format.Parse(case, pb.JsonMessageMaps())
                python_rejects = False
            except Exception:
                python_rejects = True
            if not mojo_rows[index].startswith("ERR") or not python_rejects:
                message_map_reject_ok = False
                break
    message_map_reject_detail = (
        "" if message_map_reject_ok else str(mojo_rows)
    )
    record(
        "proto",
        "proto3 JSON message-valued map rejection agreement "
        f"({len(message_map_rejected) if message_map_reject_ok else 0}/"
        f"{len(message_map_rejected)})",
        message_map_reject_ok,
        message_map_reject_detail,
    )

    message_map_unknown = (
        '{"children":{"child":{"id":1,"unknown":{"nested":true}}}}'
    )
    infile = tmp / "json_message_map_ignore_in.txt"
    outfile = tmp / "json_message_map_ignore_out.txt"
    infile.write_text(message_map_unknown + "\n")
    result = run_tool(
        "proto_json_codec",
        "parse-message-maps-ignore-unknown",
        infile,
        outfile,
    )
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    expected = json_format.Parse(
        message_map_unknown,
        pb.JsonMessageMaps(),
        ignore_unknown_fields=True,
    )
    message_map_unknown_ok = (
        has_exact_result_rows(mojo_rows, 1)
        and not mojo_rows[0].startswith("ERR")
        and pb.JsonMessageMaps.FromString(bytes.fromhex(mojo_rows[0]))
        == expected
    )
    record(
        "proto",
        "proto3 JSON message-valued map unknown field handling",
        message_map_unknown_ok,
        "" if message_map_unknown_ok else str(mojo_rows),
    )

    valid_edges = [
        '{"fInt32":2147483647}',
        '{"fInt32":-2147483648}',
        '{"fUint32":4294967295}',
        '{"fInt64":"9223372036854775807"}',
        '{"fInt64":"-9223372036854775808"}',
        '{"fUint64":"18446744073709551615"}',
        '{"fInt32":"2\\u003147483647"}',
        '{"fInt32":"1e5"}',
        '{"fInt32":100000.000}',
        '{"fBool":true}',
        '{"fFloat":"NaN"}',
        '{"fFloat":"Infinity"}',
        '{"fDouble":"-Infinity"}',
        '{"fString":"\\u8c37\\u6b4c"}',
        '{"fString":"\\uD83D\\uDE01"}',
        '{"fString":"hello\\u0000world"}',
        '{"fBytes":"AQI="}',
        '{"fBytes":"-_"}',
        '{"f_int32":7}',
        '{"fInt32":null}',
    ]
    infile = tmp / "json_valid_edges_in.txt"
    outfile = tmp / "json_valid_edges_out.txt"
    infile.write_text("".join(case + "\n" for case in valid_edges))
    result = run_tool("proto_json_codec", "parse", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    edge_row_count_ok = has_exact_result_rows(mojo_rows, len(valid_edges))
    edge_agreement = [False] * len(valid_edges)
    if edge_row_count_ok:
        for i, case in enumerate(valid_edges):
            if mojo_rows[i].startswith("ERR"):
                continue
            expected = json_format.Parse(case, pb.Scalars()).SerializeToString()
            edge_agreement[i] = bytes.fromhex(mojo_rows[i]) == expected
    edge_detail = ""
    if not edge_row_count_ok:
        edge_detail = f"expected {len(valid_edges)} rows, got {len(mojo_rows)}"
    elif not all(edge_agreement):
        edge_detail = str(list(zip(valid_edges, mojo_rows)))
    record(
        "proto",
        f"proto3 JSON accepted-edge agreement ({sum(edge_agreement)}/{len(edge_agreement)})",
        edge_row_count_ok and all(edge_agreement),
        edge_detail,
    )

    # Keep an explicit reject table because valid-message round trips do not
    # exercise strict parser behavior.
    rejected = [
        '{"fInt32":2147483648}',
        '{"fInt32":-2147483649}',
        '{"fUint32":-1}',
        '{"fUint32":4294967296}',
        '{"fInt64":9223372036854775808}',
        '{"fInt64":"9223372036854775808"}',
        '{"fInt64":-9223372036854775809}',
        '{"fInt64":"-9223372036854775809"}',
        '{"fUint64":18446744073709551616}',
        '{"fUint64":"18446744073709551616"}',
        '{"fInt32":0.5}',
        '{"fInt32":" 1"}',
        '{"fInt32":01}',
        '{"fInt32":+1}',
        '{"fFloat":NaN}',
        '{"fFloat":3.5e38}',
        '{"fDouble":1.9e308}',
        '{"fBool":1}',
        '{"fInt32":1/*comment*/}',
        '{"fString":"\\x20"}',
        '{"fString":"\\uD800"}',
        '{"fString":"\\uDC00"}',
        '{"fString":1}',
        '{"fBytes":"A"}',
        '{"fBytes":"A!"}',
        '{"fInt32":1,"fInt32":2}',
        '{"unknown":1}',
        '{"fInt32":1 "fBool":true}',
        '{"fInt32":1,}',
        '{"fInt32":1} false',
        'null',
    ]
    infile = tmp / "json_reject_in.txt"
    outfile = tmp / "json_reject_out.txt"
    infile.write_text("".join(case + "\n" for case in rejected))
    result = run_tool("proto_json_codec", "parse", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    python_rejected = []
    for case in rejected:
        try:
            json_format.Parse(case, pb.Scalars())
            python_rejected.append(False)
        except Exception:
            python_rejected.append(True)
    reject_row_count_ok = has_exact_result_rows(mojo_rows, len(rejected))
    agreement = [False] * len(rejected)
    if reject_row_count_ok:
        agreement = [
            mojo_rows[i].startswith("ERR") and python_rejected[i]
            for i in range(len(rejected))
        ]
    reject_detail = ""
    if not reject_row_count_ok:
        reject_detail = f"expected {len(rejected)} rows, got {len(mojo_rows)}"
    elif not all(agreement):
        reject_detail = str(list(zip(rejected, mojo_rows, python_rejected)))
    record(
        "proto",
        f"proto3 JSON rejection agreement ({sum(agreement)}/{len(agreement)})",
        reject_row_count_ok and all(agreement),
        reject_detail,
    )

    print(f"enum JSON differential seed: {ENUM_JSON_SEED}")
    enum_inputs = [
        '{"status":"STATUS_UNSPECIFIED"}',
        '{"status":"STATUS_ACTIVE"}',
        '{"status":"STATUS_ENABLED"}',
        '{"status":"STATUS_PAUSED"}',
        '{"status":"STATUS_NEGATIVE"}',
        '{"status":1}',
        '{"status":123}',
        '{"status":2147483647}',
        '{"status":-2147483648}',
    ]
    enum_rng = random.Random(ENUM_JSON_SEED)
    used_values = {0, 1, 2, -1, 123, 2147483647, -2147483648}
    while len(enum_inputs) < 200:
        value = enum_rng.randint(-2147483648, 2147483647)
        if value in used_values:
            continue
        used_values.add(value)
        enum_inputs.append(
            json_format.MessageToJson(pb.EnumValue(status=value), indent=None)
        )
    enum_messages = [
        json_format.Parse(text, pb.EnumValue()) for text in enum_inputs
    ]

    infile = tmp / "json_enum_parse_in.txt"
    outfile = tmp / "json_enum_parse_out.txt"
    infile.write_text(
        "".join(
            text + "\n" for text in enum_inputs
        )
    )
    result = run_tool("proto_json_codec", "parse-enum", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    enum_parse_ok = has_exact_result_rows(mojo_rows, len(enum_messages))
    enum_parse_detail = ""
    if enum_parse_ok:
        for index, row in enumerate(mojo_rows):
            if row.startswith("ERR") or (
                pb.EnumValue.FromString(bytes.fromhex(row)) != enum_messages[index]
            ):
                enum_parse_ok = False
                enum_parse_detail = f"case {index}: {row}"
                break
    else:
        enum_parse_detail = (
            f"expected {len(enum_messages)} rows, got {len(mojo_rows)}"
        )
    record(
        "proto",
        "proto3 JSON parse differential, singular enums "
        f"(n={len(enum_messages)}, seed={ENUM_JSON_SEED})",
        enum_parse_ok,
        enum_parse_detail,
    )

    infile = tmp / "json_enum_print_in.txt"
    outfile = tmp / "json_enum_print_out.txt"
    infile.write_text(
        "".join(
            (message.SerializeToString().hex() or "-") + "\n"
            for message in enum_messages
        )
    )
    result = run_tool("proto_json_codec", "print-enum", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    enum_print_ok = has_exact_result_rows(mojo_rows, len(enum_messages))
    enum_print_detail = ""
    if enum_print_ok:
        for index, row in enumerate(mojo_rows):
            try:
                actual = json.loads(row)
                expected = json.loads(json_format.MessageToJson(enum_messages[index]))
                reparsed = json_format.Parse(row, pb.EnumValue())
            except Exception as exc:
                enum_print_ok = False
                enum_print_detail = f"case {index}: {exc}"
                break
            if not json_values_equal(actual, expected) or reparsed != enum_messages[index]:
                enum_print_ok = False
                enum_print_detail = f"case {index}: {actual!r} != {expected!r}"
                break
    else:
        enum_print_detail = (
            f"expected {len(enum_messages)} rows, got {len(mojo_rows)}"
        )
    record(
        "proto",
        "proto3 JSON print differential, singular enums "
        f"(n={len(enum_messages)}, seed={ENUM_JSON_SEED})",
        enum_print_ok,
        enum_print_detail,
    )

    enum_edges = [
        '{"status":"STATUS_UNSPECIFIED"}',
        '{"status":"STATUS_ACTIVE"}',
        '{"status":"STATUS_ENABLED"}',
        '{"status":"STATUS_NEGATIVE"}',
        '{"status":123}',
        '{"status":-2147483648}',
        '{"status":null}',
    ]
    infile = tmp / "json_enum_edges_in.txt"
    outfile = tmp / "json_enum_edges_out.txt"
    infile.write_text("".join(case + "\n" for case in enum_edges))
    result = run_tool("proto_json_codec", "parse-enum", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    enum_edges_ok = has_exact_result_rows(mojo_rows, len(enum_edges))
    enum_edges_detail = ""
    if enum_edges_ok:
        for index, case in enumerate(enum_edges):
            expected = json_format.Parse(case, pb.EnumValue())
            row = mojo_rows[index]
            if row.startswith("ERR") or pb.EnumValue.FromString(bytes.fromhex(row)) != expected:
                enum_edges_ok = False
                enum_edges_detail = f"case {index}: {case} -> {row}"
                break
    else:
        enum_edges_detail = f"expected {len(enum_edges)} rows, got {len(mojo_rows)}"
    record(
        "proto",
        "proto3 JSON enum accepted-edge agreement "
        f"({len(enum_edges) if enum_edges_ok else 0}/{len(enum_edges)})",
        enum_edges_ok,
        enum_edges_detail,
    )

    enum_rejected = [
        '{"status":"STATUS_MISSING"}',
        '{"status":2147483648}',
        '{"status":-2147483649}',
        '{"status":{}}',
        '{"status":[]}',
        '{"status":"1.5"}',
    ]
    infile = tmp / "json_enum_reject_in.txt"
    outfile = tmp / "json_enum_reject_out.txt"
    infile.write_text("".join(case + "\n" for case in enum_rejected))
    result = run_tool("proto_json_codec", "parse-enum", infile, outfile)
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    enum_reject_ok = has_exact_result_rows(mojo_rows, len(enum_rejected))
    if enum_reject_ok:
        for index, case in enumerate(enum_rejected):
            try:
                json_format.Parse(case, pb.EnumValue())
                python_rejects = False
            except Exception:
                python_rejects = True
            if not mojo_rows[index].startswith("ERR") or not python_rejects:
                enum_reject_ok = False
                break
    enum_reject_detail = "" if enum_reject_ok else str(mojo_rows)
    record(
        "proto",
        "proto3 JSON enum rejection agreement "
        f"({len(enum_rejected) if enum_reject_ok else 0}/{len(enum_rejected)})",
        enum_reject_ok,
        enum_reject_detail,
    )

    ignored_enum = '{"status":"STATUS_MISSING"}'
    infile = tmp / "json_enum_ignore_in.txt"
    outfile = tmp / "json_enum_ignore_out.txt"
    infile.write_text(ignored_enum + "\n")
    result = run_tool(
        "proto_json_codec", "parse-enum-ignore-unknown", infile, outfile
    )
    mojo_rows = outfile.read_text().splitlines() if result.returncode == 0 else []
    expected = json_format.Parse(
        ignored_enum, pb.EnumValue(), ignore_unknown_fields=True
    )
    enum_ignore_ok = (
        has_exact_result_rows(mojo_rows, 1)
        and not mojo_rows[0].startswith("ERR")
        and pb.EnumValue.FromString(bytes.fromhex(mojo_rows[0])) == expected
    )
    record(
        "proto",
        "proto3 JSON unknown enum name handling",
        enum_ignore_ok,
        "" if enum_ignore_ok else str(mojo_rows),
    )


# ---------------------------------------------------------- conformance ---

CONFORMANCE_RUNNER = Path(
    os.environ.get(
        "CONFORMANCE_RUNNER",
        str(Path.home() / "dev/open-source/protobuf-conformance/build/conformance_test_runner"),
    )
)
@dataclass(frozen=True)
class ConformanceSummary:
    runner_exit_code: int
    verdict: str
    successes: int
    skipped: int
    unexpected_failures: int

    @property
    def passed(self) -> bool:
        return (
            self.runner_exit_code == 0
            and self.verdict == "PASSED"
            and self.successes == EXPECTED_BINARY_CONFORMANCE_SUCCESSES
            and self.unexpected_failures == 0
        )


def section_conformance(tmp: Path) -> ConformanceSummary | None:
    """Google's official protobuf conformance suite (binary wire format)."""
    if not CONFORMANCE_RUNNER.exists():
        print("== protobuf conformance: runner not available, section skipped ==")
        return None
    print("== Google protobuf conformance suite ==")
    subprocess.run(
        ["mojo", "build", "-I", "src", "-I", "conformance/gen",
         "conformance/conformance_testee.mojo", "-o", str(BUILD / "conformance_testee")],
        check=True, cwd=ROOT)
    r = subprocess.run(
        [str(CONFORMANCE_RUNNER), "--enforce_recommended", str(BUILD / "conformance_testee")],
        capture_output=True, text=True, timeout=900, cwd=ROOT)
    sums = re.findall(
        r"CONFORMANCE SUITE (PASSED|FAILED): (\d+) successes, (\d+) skipped, "
        r"(\d+) expected failures, (\d+) unexpected failures", r.stdout + r.stderr)
    if not sums:
        record(
            "proto", "protobuf conformance suite", False,
            f"no summary parsed (rc={r.returncode}); "
            f"stderr: {r.stderr[-400:]!r} stdout: {r.stdout[-200:]!r}")
        return None
    # First summary = binary+JSON suite; second = text-format suite.
    verdict, successes, skipped, _, failures = sums[0]
    summary = ConformanceSummary(
        runner_exit_code=r.returncode,
        verdict=verdict,
        successes=int(successes),
        skipped=int(skipped),
        unexpected_failures=int(failures),
    )
    ok = r.returncode == 0 and summary.passed
    detail = ""
    if not ok:
        detail = (
            f"expected exactly {EXPECTED_BINARY_CONFORMANCE_SUCCESSES} successes "
            f"and 0 unexpected failures; {r.stdout[-300:]}"
        )
    record(
        "proto",
        f"Google conformance, binary wire format ({summary.successes} passed, "
        f"{summary.unexpected_failures} failed; {summary.skipped} skipped = "
        "official JSON group, proto2, and editions, declared unsupported)",
        ok,
        detail,
    )
    return summary


def conformance_badge_payload(
    summary: ConformanceSummary | None,
    validation: ResultRegistryValidation,
) -> dict[str, object]:
    """Builds a badge that turns green only for one complete passing run."""
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "label": "protobuf conformance",
    }
    if not validation.registry_ok:
        payload.update(message="result registry invalid", color="red")
    elif not validation.all_ok:
        payload.update(
            message=(f"{validation.passed_count}/{validation.expected_count} checks"),
            color="red",
        )
    elif summary is None:
        payload.update(message="official suite missing", color="red")
    else:
        total = summary.successes + summary.unexpected_failures
        payload.update(
            message=f"{summary.successes}/{total} binary proto3",
            color="brightgreen" if summary.passed else "red",
        )
    return payload


def write_conformance_badge(
    summary: ConformanceSummary | None,
    validation: ResultRegistryValidation,
    *,
    path: Path | None = None,
    announce: bool = True,
):
    """Writes the Shields endpoint for the validated result set."""
    payload = conformance_badge_payload(summary, validation)
    output = CONFORMANCE_BADGE if path is None else path
    output.write_text(json.dumps(payload, indent=2) + "\n")
    if announce:
        print(f"report: {output}")


# --------------------------------------------------------------- report ---


def versions() -> dict[str, str]:
    import google.protobuf

    mojo = subprocess.run(
        ["mojo", "--version"], capture_output=True, text=True, cwd=ROOT
    ).stdout.strip()
    return {
        "mojo": mojo,
        "python": platform.python_version(),
        "protobuf (reference for proto)": google.protobuf.__version__,
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
    }


def markdown_verdict(validation: ResultRegistryValidation, now: str) -> str:
    """Formats the Markdown verdict without hiding registry errors."""
    if validation.registry_ok:
        result = f"{validation.passed_count}/{validation.expected_count} checks passed"
    else:
        result = (
            "invalid result set. "
            f"{validation.passed_count}/{validation.expected_count} "
            "registered checks passed"
        )
    return f"**Result: {result}.** Generated {now}."


def html_verdict(validation: ResultRegistryValidation, now: str) -> str:
    """Formats the HTML verdict with a failing class unless every row passed."""
    css_class = "" if validation.all_ok else " failing"
    if validation.registry_ok:
        score = f"{validation.passed_count}/{validation.expected_count}"
        label = "checks passed"
    else:
        score = "invalid"
        label = (
            f"{validation.passed_count}/{validation.expected_count} "
            "registered checks passed"
        )
    return (
        f'<div class="verdict"><span class="score{css_class}">{score}</span>'
        f"<span>{label}</span>"
        f'<span class="when">{now}</span></div>'
    )


def write_report(
    validation: ResultRegistryValidation,
    *,
    results: ResultRows | None = None,
    path: Path | None = None,
    environment: dict[str, str] | None = None,
    now: str | None = None,
    announce: bool = True,
) -> bool:
    report_results = RESULTS if results is None else results
    output = REPORT if path is None else path
    report_environment = versions() if environment is None else environment
    generated_at = (
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if now is None
        else now
    )
    lines = [
        "# protomojo Compliance Report",
        "",
        "<!-- Generated by compliance/run_compliance.py. Do not edit. -->",
        "<!-- Regenerate with: pixi run compliance -->",
        "",
        markdown_verdict(validation, generated_at),
        "",
        "Every check compares protomojo against Python `protobuf` (the",
        "reference implementation), never against itself. Google's official",
        "conformance suite supplies one required registered check.",
        "",
        "## Environment",
        "",
        "| Component | Version |",
        "|---|---|",
    ]
    for k, v in report_environment.items():
        lines.append(f"| {k} | {v} |")
    if validation.errors:
        lines += [
            "",
            "## Report integrity",
            "",
            "The result registry did not match the expected 15 checks:",
            "",
        ]
        lines.extend(f"- {error}" for error in validation.errors)
    for section, rows in report_results.items():
        if section in EXPECTED_RESULT_ROWS:
            p, expected = section_result_counts(report_results, section)
            section_score = f"{p}/{expected}"
        else:
            section_score = "invalid"
        lines += [
            "",
            f"## `{section}` vs Python protobuf: {section_score}",
            "",
            "| Check | Result |",
            "|---|---|",
        ]
        for name, ok, detail in rows:
            status = "✅ pass" if ok else f"❌ **fail**: {detail[:160]}"
            lines.append(f"| {name} | {status} |")
    lines += [
        "",
        "## How to rerun",
        "",
        "```sh",
        "pixi run compliance   # from this package root",
        "```",
        "",
        "The Google conformance section needs `conformance_test_runner`",
        "(env `CONFORMANCE_RUNNER`). A missing runner leaves the result set",
        "incomplete and fails the report.",
        "",
    ]
    output.write_text("\n".join(lines))
    if announce:
        if validation.registry_ok:
            print(
                "\ncompliance: "
                f"{validation.passed_count}/{validation.expected_count} "
                "checks passed"
            )
        else:
            print(
                "\ncompliance: invalid result set "
                f"({validation.passed_count}/{validation.expected_count} "
                "registered checks passed)"
            )
        print(f"report: {output}")
    return validation.all_ok


HTML_REPORT = ROOT / "COMPLIANCE.html"

HTML_HEAD = """<!-- GENERATED by compliance/run_compliance.py - regenerate with: pixi run compliance -->
<title>protomojo Compliance</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@600&display=swap">
<style>
:root {
  --paper: #FAFAF8; --ink: #22262B; --muted: #6E6A62; --accent: #C2551F;
  --pass: #2E7D4F; --fail: #B3362B; --line: #E4E0D8; --panel: #F2F0EA;
  --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
  --sans: "IBM Plex Sans", -apple-system, "Segoe UI", sans-serif;
  --cond: "IBM Plex Sans Condensed", "Arial Narrow", var(--sans);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #16181C; --ink: #E8E6E1; --muted: #98938A; --accent: #E0663A;
    --pass: #5EC08D; --fail: #E5776C; --line: #2C2F35; --panel: #1D2025;
  }
}
:root[data-theme="dark"] {
  --paper: #16181C; --ink: #E8E6E1; --muted: #98938A; --accent: #E0663A;
  --pass: #5EC08D; --fail: #E5776C; --line: #2C2F35; --panel: #1D2025;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 16px/1.6 var(--sans); -webkit-font-smoothing: antialiased; }
main { max-width: 76ch; margin: 0 auto; padding: 3.5rem 1.5rem 5rem; }
header { border-bottom: 2px solid var(--ink); padding-bottom: 1.75rem; margin-bottom: 2.5rem; }
.eyebrow { font: 500 0.72rem/1 var(--mono); letter-spacing: 0.14em; text-transform: uppercase; color: var(--accent); margin: 0 0 0.9rem; }
h1 { font: 600 clamp(1.9rem, 5vw, 2.6rem)/1.1 var(--cond); margin: 0 0 1.1rem; text-wrap: balance; letter-spacing: -0.01em; }
.verdict { display: flex; align-items: baseline; gap: 0.75rem; flex-wrap: wrap; }
.verdict .score { font: 500 2rem/1 var(--mono); font-variant-numeric: tabular-nums; color: var(--pass); }
.verdict .score.failing { color: var(--fail); }
.verdict .when { color: var(--muted); font-size: 0.85rem; }
.thesis { color: var(--muted); margin: 0.9rem 0 0; max-width: 62ch; }
.scorecard { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1.5rem; padding: 0; list-style: none; }
.scorecard li { font: 400 0.78rem/1 var(--mono); padding: 0.45rem 0.7rem; border: 1px solid var(--line); border-radius: 3px; background: var(--panel); display: flex; gap: 0.55rem; align-items: center; }
.scorecard .n { font-variant-numeric: tabular-nums; color: var(--pass); font-weight: 500; }
.scorecard .n.failing { color: var(--fail); }
section { margin: 2.75rem 0; }
h2 { font: 600 1.15rem/1.3 var(--sans); margin: 0 0 0.35rem; text-wrap: balance; }
h2 .pkg { font-family: var(--mono); font-weight: 500; color: var(--accent); }
.vs { color: var(--muted); font-weight: 400; }
.method { color: var(--muted); font-size: 0.88rem; margin: 0 0 1.1rem; max-width: 68ch; }
.tablewrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 0.88rem; }
th { text-align: left; font: 500 0.7rem/1 var(--mono); letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); padding: 0 0.75rem 0.5rem 0; border-bottom: 1px solid var(--ink); }
td { padding: 0.5rem 0.75rem 0.5rem 0; border-bottom: 1px solid var(--line); vertical-align: top; }
td.result { white-space: nowrap; font: 500 0.78rem/1.8 var(--mono); }
.pass { color: var(--pass); }
.fail { color: var(--fail); }
td .detail { display: block; color: var(--muted); font-size: 0.8rem; }
.envtable td:first-child { color: var(--muted); width: 40%; }
.envtable td { font-family: var(--mono); font-size: 0.8rem; }
.gaps { border-left: 3px solid var(--accent); background: var(--panel); padding: 1.1rem 1.4rem; }
.gaps h2 { margin-top: 0; }
.gaps ul { margin: 0.5rem 0 0; padding-left: 1.1rem; }
.gaps li { margin: 0.45rem 0; font-size: 0.9rem; }
.gaps strong { font-weight: 600; }
footer { margin-top: 3rem; color: var(--muted); font: 400 0.78rem/1.6 var(--mono); border-top: 1px solid var(--line); padding-top: 1rem; }
code { font-family: var(--mono); font-size: 0.92em; }
</style>
"""


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


HTML_EYEBROW = "protomojo &middot; differential compliance run"
HTML_H1 = "Protobuf data judged by the reference implementation"
HTML_THESIS = (
    "No self-grading: Python <code>protobuf</code> judges seeded binary and "
    "flat, nested, and repeated JSON messages in both directions. "
    "Google&rsquo;s official conformance "
    "suite covers the supported binary wire format."
)
HTML_GAPS = [
    (
        "Structured JSON mapping",
        "scalar, enum, and ordinary message fields may be singular or "
        "repeated; maps, oneofs, presence, recursive message cycles, and "
        "well-known types remain unsupported.",
    ),
    ("proto2 / editions", "proto3 only; groups and extensions are rejected, never mis-parsed."),
    ("Text format", "not implemented."),
]
HTML_SECTIONS = {
    "proto": (
        "`proto` vs Python `protobuf` + Google conformance",
        "Python protobuf checks seeded binary, flat JSON, nested JSON, and "
        "repeated JSON messages in both directions. Malformed input must be "
        "rejected in agreement, and "
        "Google's conformance_test_runner drives the binary wire-format suite.",
    ),
}


def write_html_report(
    validation: ResultRegistryValidation,
    *,
    results: ResultRows | None = None,
    path: Path | None = None,
    environment: dict[str, str] | None = None,
    now: str | None = None,
    announce: bool = True,
):
    report_results = RESULTS if results is None else results
    output = HTML_REPORT if path is None else path
    report_environment = versions() if environment is None else environment
    generated_at = (
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if now is None
        else now
    )
    h = [HTML_HEAD, "<main>", "<header>"]
    h.append(f'<p class="eyebrow">{HTML_EYEBROW}</p>')
    h.append(f"<h1>{HTML_H1}</h1>")
    h.append(html_verdict(validation, generated_at))
    h.append(f'<p class="thesis">{HTML_THESIS}</p>')
    h.append('<ul class="scorecard">')
    for section, rows in report_results.items():
        if section in EXPECTED_RESULT_ROWS:
            p, expected = section_result_counts(report_results, section)
            section_score = f"{p}/{expected}"
        else:
            section_score = "invalid"
        cls = "" if validation.all_ok else " failing"
        h.append(
            f'<li>{esc(section)} <span class="n{cls}">'
            f"{section_score}</span></li>"
        )
    h.append("</ul></header>")

    if validation.errors:
        h.append('<section class="gaps"><h2>Report integrity</h2><ul>')
        for error in validation.errors:
            h.append(f"<li>{esc(error)}</li>")
        h.append("</ul></section>")

    for section, rows in report_results.items():
        title, blurb = HTML_SECTIONS.get(section, (section, ""))
        pkg, _, ref = title.replace("`", "").partition(" vs ")
        h.append("<section>")
        if ref:
            h.append(
                f'<h2><span class="pkg">{esc(pkg)}</span> <span class="vs">vs</span> {esc(ref)}</h2>'
            )
        else:
            h.append(f"<h2>{esc(pkg)}</h2>")
        if blurb:
            h.append(f'<p class="method">{esc(blurb)}</p>')
        h.append('<div class="tablewrap"><table>')
        h.append("<tr><th>Check</th><th>Result</th></tr>")
        for name, ok, detail in rows:
            cell = (
                '<span class="pass">PASS</span>'
                if ok
                else '<span class="fail">FAIL</span>'
            )
            extra = "" if ok else f'<span class="detail">{esc(detail[:200])}</span>'
            h.append(
                f'<tr><td>{esc(name)}</td><td class="result">{cell}{extra}</td></tr>'
            )
        h.append("</table></div></section>")

    h.append("<section><h2>Environment</h2>")
    h.append('<div class="tablewrap"><table class="envtable">')
    for k, v in report_environment.items():
        h.append(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>")
    h.append("</table></div></section>")

    h.append('<section class="gaps"><h2>Known gaps (tracked, not silent)</h2><ul>')
    for k, v in HTML_GAPS:
        h.append(f"<li><strong>{esc(k)}</strong>: {esc(v)}</li>")
    h.append("</ul></section>")
    h.append(
        "<footer>Generated by compliance/run_compliance.py &middot; "
        "rerun with <code>pixi run compliance</code> &middot; canonical copy: "
        "COMPLIANCE.md</footer>"
    )
    h.append("</main>")
    output.write_text("\n".join(h))
    if announce:
        print(f"report: {output}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--json",
        type=Path,
        default=None,
        help="dump {'sections': ...} JSON for the umbrella suite",
    )
    args = ap.parse_args()
    build_tools()
    with tempfile.TemporaryDirectory(prefix="protomojo_compliance_") as tmp_s:
        tmp = Path(tmp_s)
        compile_test_protos(tmp)
        section_proto(tmp)
        section_proto_json(tmp)
        conformance_summary = section_conformance(tmp)
    validation = validate_result_registry(RESULTS)
    for error in validation.errors:
        print(f"  FAIL [registry] {error}")
    ok = write_report(validation)
    write_html_report(validation)
    write_conformance_badge(conformance_summary, validation)
    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "sections": {
                        s: [[n, o, d] for n, o, d in rows]
                        for s, rows in RESULTS.items()
                    }
                }
            )
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
