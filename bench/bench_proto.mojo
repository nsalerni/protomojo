# ===----------------------------------------------------------------------=== #
# Copyright (c) 2026 the grpc-mojo contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
# ===----------------------------------------------------------------------=== #

"""Throughput benchmarks for the protobuf wire codec.

Run: `pixi run bench` (or directly with `mojo run -I src -I test`).
Pass `--smoke` to run each benchmark for a few milliseconds only — used by
CI to prove the benchmarks build and run without spending minutes on them.
"""

from std.benchmark import Unit, run
from std.sys import argv

from proto import WireReader, WireWriter, decode, encode
from proto_messages import Nested, Scalars


def is_smoke() -> Bool:
    for a in argv():
        if a == "--smoke":
            return True
    return False


def bench_time() -> Float64:
    return 0.005 if is_smoke() else 0.5


def run_capped[F: def() raises](f: F, secs: Float64) raises -> Float64:
    """Runs a benchmark bounded by `secs` and returns the mean in ns.

    `std.benchmark.run` keeps iterating until max_runtime_secs by default;
    cap both bounds so smoke runs stay fast.
    """
    var report = run(f, min_runtime_secs=secs, max_runtime_secs=secs * 3)
    return report.mean(Unit.ns)


def report_line(name: StringSpan, ns_per_op: Float64, bytes_per_op: Int):
    var mib_s = 0.0
    if ns_per_op > 0:
        mib_s = (Float64(bytes_per_op) / (1024 * 1024)) / (ns_per_op / 1e9)
    print(
        String(name),
        ": ",
        Int(ns_per_op),
        " ns/op",
        ", ",
        Int(mib_s),
        " MiB/s",
        sep="",
    )


def make_scalars() -> Scalars:
    var m = Scalars()
    m.f_int32 = 123456
    m.f_int64 = -987654321
    m.f_uint64 = 1 << 60
    m.f_sint32 = -1
    m.f_bool = True
    m.f_double = 3.14159
    m.f_string = "the quick brown fox jumps over the lazy dog"
    var payload = List[Byte]()
    payload.resize(64, 0xAB)
    m.f_bytes = payload^
    return m^


def make_nested() raises -> Nested:
    var n = Nested()
    var inner = make_scalars()
    n.inner = inner^
    for i in range(64):
        n.packed_ints.append(Int32(i * 7))
        n.names.append(String("name-") + String(i))
    n.counts["alpha"] = 1
    n.counts["beta"] = 2
    return n^


def main() raises:
    var secs = bench_time()

    # --- varint coding ---
    var w0 = WireWriter()
    for i in range(1000):
        w0.varint(UInt64(1) << UInt64(i % 63))
    var varint_buf = w0^.take()

    def varint_encode() raises:
        var w = WireWriter()
        for i in range(1000):
            w.varint(UInt64(1) << UInt64(i % 63))
        var out = w^.take()
        if len(out) == 0:
            raise Error("unreachable")

    var r = run_capped(varint_encode, secs)
    report_line("varint encode x1000", r / 1000, 9)

    def varint_decode() raises {varint_buf}:
        var rd = WireReader(Span(varint_buf))
        var acc = UInt64(0)
        while not rd.done():
            acc |= rd.varint()
        if acc == 0:
            raise Error("unreachable")

    r = run_capped(varint_decode, secs)
    report_line("varint decode x1000", r / 1000, 9)

    # --- message encode/decode: flat scalars ---
    var scalars = make_scalars()
    var scalars_bytes = encode(scalars)
    var scalars_size = len(scalars_bytes)
    print("scalars message size: ", scalars_size, " bytes", sep="")

    def scalars_encode() raises {scalars}:
        var out = encode(scalars)
        if len(out) == 0:
            raise Error("unreachable")

    r = run_capped(scalars_encode, secs)
    report_line("scalars encode", r, scalars_size)

    def scalars_decode() raises {scalars_bytes}:
        var m = decode[Scalars](Span(scalars_bytes))
        if m.f_int32 == 0:
            raise Error("unreachable")

    r = run_capped(scalars_decode, secs)
    report_line("scalars decode", r, scalars_size)

    # --- message encode/decode: nested + repeated + map ---
    var nested = make_nested()
    var nested_bytes = encode(nested)
    var nested_size = len(nested_bytes)
    print("nested message size: ", nested_size, " bytes", sep="")

    def nested_encode() raises {nested}:
        var out = encode(nested)
        if len(out) == 0:
            raise Error("unreachable")

    r = run_capped(nested_encode, secs)
    report_line("nested encode", r, nested_size)

    def nested_decode() raises {nested_bytes}:
        var m = decode[Nested](Span(nested_bytes))
        if len(m.packed_ints) == 0:
            raise Error("unreachable")

    r = run_capped(nested_decode, secs)
    report_line("nested decode", r, nested_size)

    print("bench_proto: done")
