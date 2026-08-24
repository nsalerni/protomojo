#!/usr/bin/env python3
"""Regression tests for proto3 JSON compliance result evaluation."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "compliance"))

from run_compliance import has_exact_result_rows, json_values_equal


def main() -> None:
    reference = {
        "fInt32": 1,
        "fInt64": "9223372036854775807",
        "fBytes": "+/8=",
    }
    assert json_values_equal(reference, reference.copy())

    numeric_int64 = reference | {"fInt64": 9223372036854775807}
    assert not json_values_equal(numeric_int64, reference)

    snake_case = reference | {"f_int32": reference["fInt32"]}
    del snake_case["fInt32"]
    assert not json_values_equal(snake_case, reference)

    unpadded_bytes = reference | {"fBytes": "+/8"}
    assert not json_values_equal(unpadded_bytes, reference)

    url_safe_bytes = reference | {"fBytes": "-_8="}
    assert not json_values_equal(url_safe_bytes, reference)

    float_shaped_integer = reference | {"fInt32": 1.0}
    assert not json_values_equal(float_shaped_integer, reference)

    assert has_exact_result_rows(["first", "second"], 2)
    assert not has_exact_result_rows(["first"], 2)
    assert not has_exact_result_rows(["first", "second", "extra"], 2)

    print("test_json_compliance_evaluator: all tests passed")


if __name__ == "__main__":
    main()
