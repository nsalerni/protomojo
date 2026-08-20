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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # package root
BUILD = ROOT / "build"
TOOLS = ROOT / "compliance" / "tools"
REPORT = ROOT / "COMPLIANCE.md"

RESULTS: dict[str, list[tuple[str, bool, str]]] = {}


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


# ---------------------------------------------------------- conformance ---

CONFORMANCE_RUNNER = Path(
    os.environ.get(
        "CONFORMANCE_RUNNER",
        str(Path.home() / "dev/open-source/protobuf-conformance/build/conformance_test_runner"),
    )
)


def section_conformance(tmp: Path):
    """Google's official protobuf conformance suite (binary wire format)."""
    if not CONFORMANCE_RUNNER.exists():
        print("== protobuf conformance: runner not available, section skipped ==")
        return
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
        return
    # First summary = binary+JSON suite; second = text-format suite.
    verdict, succ, skipped, _, failed = sums[0]
    record("proto",
           f"Google conformance, binary wire format ({succ} passed, {failed} failed; "
           f"{skipped} skipped = JSON/proto2/editions, declared unsupported)",
           verdict == "PASSED" and int(succ) > 0, r.stdout[-300:])


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
        "<!-- GENERATED by compliance/run_compliance.py — do not edit. -->",
        "<!-- Regenerate with: pixi run compliance -->",
        "",
        f"**Result: {passed}/{total} checks passed.** Generated {now}.",
        "",
        "Every check compares protomojo against Python `protobuf` (the",
        "reference implementation) — never against itself. Google's official",
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
        lines += ["", f"## `{section}` vs Python protobuf — {p}/{len(rows)}", "",
                  "| Check | Result |", "|---|---|"]
        for name, ok, detail in rows:
            status = "✅ pass" if ok else f"❌ **fail** — {detail[:160]}"
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
        section_conformance(tmp)
    ok = write_report()
    if args.json:
        args.json.write_text(json.dumps(
            {"sections": {s: [[n, o, d] for n, o, d in rows]
                          for s, rows in RESULTS.items()}}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
