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
import os
import platform
import random
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # package root
BUILD = ROOT / "build"
TOOLS = ROOT / "compliance" / "tools"
REPORT = ROOT / "COMPLIANCE.md"
CONFORMANCE_BADGE = ROOT / "conformance-badge.json"

RESULTS: dict[str, list[tuple[str, bool, str]]] = {}
ENUM_JSON_SEED = 20260824


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
        infile = tmp / f"{kind}_in.txt"
        outfile = tmp / f"{kind}_out.txt"
        infile.write_text("".join(m.SerializeToString().hex() + "\n" for m in msgs))
        r = run_tool("proto_codec", kind, infile, outfile)
        if r.returncode != 0:
            record("proto", f"differential {kind} (n={count})", False, r.stderr[:200])
            continue
        lines = outfile.read_text().splitlines()
        cls = pb.Scalars if kind == "scalars" else pb.Nested
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
    malformed = ["08", "0880808080808080808080", "0a05616263", "1d0000", "0c00"]
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
    """Compare supported flat JSON mappings with Python protobuf."""
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
EXPECTED_BINARY_CONFORMANCE_SUCCESSES = 698


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


def write_conformance_badge(summary: ConformanceSummary | None):
    """Write a Shields endpoint only when the official runner was executed."""
    if summary is None:
        return
    total = summary.successes + summary.unexpected_failures
    payload = {
        "schemaVersion": 1,
        "label": "protobuf conformance",
        "message": f"{summary.successes}/{total} binary proto3",
        "color": "brightgreen" if summary.passed else "red",
    }
    CONFORMANCE_BADGE.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"report: {CONFORMANCE_BADGE.relative_to(ROOT)}")


# --------------------------------------------------------------- report ---

def versions() -> dict[str, str]:
    import google.protobuf
    mojo = subprocess.run(["mojo", "--version"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    return {
        "mojo": mojo,
        "python": platform.python_version(),
        "protobuf (reference for proto)": google.protobuf.__version__,
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
    }


def write_report() -> bool:
    total = sum(len(v) for v in RESULTS.values())
    passed = sum(1 for v in RESULTS.values() for _, ok, _ in v if ok)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# protomojo Compliance Report",
        "",
        "<!-- Generated by compliance/run_compliance.py. Do not edit. -->",
        "<!-- Regenerate with: pixi run compliance -->",
        "",
        f"**Result: {passed}/{total} checks passed.** Generated {now}.",
        "",
        "Every check compares protomojo against Python `protobuf` (the",
        "reference implementation), never against itself. Google's official",
        "conformance suite runs when its runner binary is present.",
        "",
        "## Environment",
        "",
        "| Component | Version |",
        "|---|---|",
    ]
    for k, v in versions().items():
        lines.append(f"| {k} | {v} |")
    for section, rows in RESULTS.items():
        p = sum(1 for _, ok, _ in rows if ok)
        lines += ["", f"## `{section}` vs Python protobuf: {p}/{len(rows)}", "",
                  "| Check | Result |", "|---|---|"]
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
        "(env `CONFORMANCE_RUNNER`); it is skipped politely when absent.",
        "",
    ]
    REPORT.write_text("\n".join(lines))
    print(f"\ncompliance: {passed}/{total} checks passed")
    print(f"report: {REPORT}")
    return passed == total


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
    "flat JSON messages in both directions. Google&rsquo;s official conformance "
    "suite covers the supported binary wire format."
)
HTML_GAPS = [
    (
        "Structured JSON mapping",
        "singular primitive and enum fields are supported; nested messages, "
        "repeated fields, maps, oneofs, presence, and well-known types remain "
        "unsupported.",
    ),
    ("proto2 / editions", "proto3 only; groups and extensions are rejected, never mis-parsed."),
    ("Text format", "not implemented."),
]
HTML_SECTIONS = {
    "proto": (
        "`proto` vs Python `protobuf` + Google conformance",
        "Python protobuf checks seeded binary and flat JSON messages in both "
        "directions. Malformed input must be rejected in agreement, and "
        "Google's conformance_test_runner drives the binary wire-format suite.",
    ),
}


def write_html_report():
    total = sum(len(v) for v in RESULTS.values())
    passed = sum(1 for v in RESULTS.values() for _, ok, _ in v if ok)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    all_ok = passed == total
    h = [HTML_HEAD, "<main>", "<header>"]
    h.append(f'<p class="eyebrow">{HTML_EYEBROW}</p>')
    h.append(f"<h1>{HTML_H1}</h1>")
    h.append(
        f'<div class="verdict"><span class="score{"" if all_ok else " failing"}">'
        f"{passed}/{total}</span><span>checks passed</span>"
        f'<span class="when">{now}</span></div>'
    )
    h.append(f'<p class="thesis">{HTML_THESIS}</p>')
    h.append('<ul class="scorecard">')
    for section, rows in RESULTS.items():
        p = sum(1 for _, ok, _ in rows if ok)
        cls = "" if p == len(rows) else " failing"
        h.append(f'<li>{esc(section)} <span class="n{cls}">{p}/{len(rows)}</span></li>')
    h.append("</ul></header>")

    for section, rows in RESULTS.items():
        title, blurb = HTML_SECTIONS.get(section, (section, ""))
        pkg, _, ref = title.replace("`", "").partition(" vs ")
        h.append("<section>")
        if ref:
            h.append(f'<h2><span class="pkg">{esc(pkg)}</span> <span class="vs">vs</span> {esc(ref)}</h2>')
        else:
            h.append(f"<h2>{esc(pkg)}</h2>")
        if blurb:
            h.append(f'<p class="method">{esc(blurb)}</p>')
        h.append('<div class="tablewrap"><table>')
        h.append("<tr><th>Check</th><th>Result</th></tr>")
        for name, ok, detail in rows:
            cell = '<span class="pass">PASS</span>' if ok else '<span class="fail">FAIL</span>'
            extra = "" if ok else f'<span class="detail">{esc(detail[:200])}</span>'
            h.append(f"<tr><td>{esc(name)}</td><td class=\"result\">{cell}{extra}</td></tr>")
        h.append("</table></div></section>")

    h.append("<section><h2>Environment</h2>")
    h.append('<div class="tablewrap"><table class="envtable">')
    for k, v in versions().items():
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
    HTML_REPORT.write_text("\n".join(h))
    print(f"report: {HTML_REPORT.relative_to(ROOT)}")



def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None,
                    help="dump {'sections': ...} JSON for the umbrella suite")
    args = ap.parse_args()
    build_tools()
    with tempfile.TemporaryDirectory(prefix="protomojo_compliance_") as tmp_s:
        tmp = Path(tmp_s)
        compile_test_protos(tmp)
        section_proto(tmp)
        section_proto_json(tmp)
        conformance_summary = section_conformance(tmp)
    ok = write_report()
    write_html_report()
    write_conformance_badge(conformance_summary)
    if args.json:
        args.json.write_text(json.dumps(
            {"sections": {s: [[n, o, d] for n, o, d in rows]
                          for s, rows in RESULTS.items()}}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
