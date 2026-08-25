#!/usr/bin/env python3
"""Regression tests for proto3 JSON compliance result evaluation."""

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "compliance"))

from run_compliance import (
    ConformanceSummary,
    EXPECTED_RESULT_ROWS,
    ResultRegistryValidation,
    conformance_badge_payload,
    has_exact_result_rows,
    html_verdict,
    json_values_equal,
    markdown_verdict,
    validate_result_registry,
    write_conformance_badge,
    write_html_report,
    write_report,
)

TOTAL_RESULTS = 92
REGISTERED_TOTAL_RESULTS = sum(
    len(rows) for rows in EXPECTED_RESULT_ROWS.values()
)


def complete_results() -> dict[str, list[tuple[str, bool, str]]]:
    return {
        section: [(name, True, "") for name in names]
        for section, names in EXPECTED_RESULT_ROWS.items()
    }


def generated_outputs(
    results: dict[str, list[tuple[str, bool, str]]],
    validation: ResultRegistryValidation,
) -> tuple[str, str, dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix="protomojo-report-test-") as temp:
        root = Path(temp)
        markdown_path = root / "COMPLIANCE.md"
        html_path = root / "COMPLIANCE.html"
        badge_path = root / "conformance-badge.json"
        write_report(
            validation,
            results=results,
            path=markdown_path,
            environment={"test": "1"},
            now="test time",
            announce=False,
        )
        write_html_report(
            validation,
            results=results,
            path=html_path,
            environment={"test": "1"},
            now="test time",
            announce=False,
        )
        write_conformance_badge(
            passing_summary(), validation, path=badge_path, announce=False
        )
        return (
            markdown_path.read_text(),
            html_path.read_text(),
            json.loads(badge_path.read_text()),
        )


def assert_invalid_outputs(
    results: dict[str, list[tuple[str, bool, str]]],
    expected_error: str,
) -> None:
    validation = validate_result_registry(results)
    assert not validation.registry_ok
    assert not validation.all_ok
    assert any(expected_error in error for error in validation.errors)

    markdown = markdown_verdict(validation, "test time")
    assert "invalid result set" in markdown
    complete_markdown = (
        f"**Result: {TOTAL_RESULTS}/{TOTAL_RESULTS} checks passed.**"
    )
    assert complete_markdown not in markdown

    html = html_verdict(validation, "test time")
    assert '<span class="score failing">invalid</span>' in html
    complete_html = (
        f'<span class="score">{TOTAL_RESULTS}/{TOTAL_RESULTS}</span>'
    )
    assert complete_html not in html

    badge = conformance_badge_payload(passing_summary(), validation)
    assert badge["color"] == "red"
    assert badge["message"] == "result registry invalid"

    markdown, html, badge = generated_outputs(results, validation)
    assert "invalid result set" in markdown
    assert complete_markdown not in markdown
    assert f"{TOTAL_RESULTS + 1}/{TOTAL_RESULTS}" not in markdown
    assert '<span class="score failing">invalid</span>' in html
    assert complete_html not in html
    assert f"{TOTAL_RESULTS + 1}/{TOTAL_RESULTS}" not in html
    assert badge["color"] == "red"


def passing_summary() -> ConformanceSummary:
    return ConformanceSummary(
        runner_exit_code=0,
        verdict="PASSED",
        successes=1476,
        skipped=1303,
        unexpected_failures=0,
    )


def test_result_registry() -> None:
    assert passing_summary().passed
    wrong_skips = ConformanceSummary(
        runner_exit_code=0,
        verdict="PASSED",
        successes=1476,
        skipped=1302,
        unexpected_failures=0,
    )
    assert not wrong_skips.passed
    wrong_skip_badge = conformance_badge_payload(
        wrong_skips, validate_result_registry(complete_results())
    )
    assert wrong_skip_badge["color"] == "red"
    assert wrong_skip_badge["message"] == "1476 passed, 1302 skipped"

    assert REGISTERED_TOTAL_RESULTS == TOTAL_RESULTS
    complete = complete_results()
    validation = validate_result_registry(complete)
    assert validation.registry_ok
    assert validation.all_ok
    assert validation.passed_count == TOTAL_RESULTS
    assert validation.expected_count == TOTAL_RESULTS
    complete_markdown = (
        f"**Result: {TOTAL_RESULTS}/{TOTAL_RESULTS} checks passed.**"
    )
    complete_html = (
        f'<span class="score">{TOTAL_RESULTS}/{TOTAL_RESULTS}</span>'
    )
    assert complete_markdown in markdown_verdict(validation, "test time")
    assert complete_html in html_verdict(validation, "test time")
    passing_badge = conformance_badge_payload(passing_summary(), validation)
    assert passing_badge["color"] == "brightgreen"
    assert passing_badge["message"] == "1476/1476 proto3 binary + JSON"
    markdown, html, badge = generated_outputs(complete, validation)
    assert complete_markdown in markdown
    assert complete_html in html
    assert badge["color"] == "brightgreen"

    failed = complete_results()
    first_name = EXPECTED_RESULT_ROWS["proto"][0]
    failed["proto"][0] = (first_name, False, "reference mismatch")
    failed_validation = validate_result_registry(failed)
    assert failed_validation.registry_ok
    assert not failed_validation.all_ok
    assert failed_validation.passed_count == TOTAL_RESULTS - 1
    failed_markdown = (
        f"**Result: {TOTAL_RESULTS - 1}/{TOTAL_RESULTS} checks passed.**"
    )
    failed_html = (
        f'<span class="score failing">{TOTAL_RESULTS - 1}/'
        f'{TOTAL_RESULTS}</span>'
    )
    assert failed_markdown in markdown_verdict(failed_validation, "test time")
    assert failed_html in html_verdict(failed_validation, "test time")
    assert (
        conformance_badge_payload(passing_summary(), failed_validation)["color"]
        == "red"
    )
    markdown, html, badge = generated_outputs(failed, failed_validation)
    assert failed_markdown in markdown
    assert failed_html in html
    assert badge["color"] == "red"

    missing = complete_results()
    _ = missing["proto"].pop()
    assert_invalid_outputs(missing, "missing row")

    missing_section = complete_results()
    del missing_section["proto"]
    assert_invalid_outputs(missing_section, "missing section: proto")

    duplicate = complete_results()
    duplicate["proto"].append(duplicate["proto"][0])
    assert_invalid_outputs(duplicate, "duplicate row")

    unexpected = complete_results()
    unexpected["proto"].append(("unexpected check", True, ""))
    assert_invalid_outputs(unexpected, "unexpected row")

    unknown_section = complete_results()
    unknown_section["other"] = [("other check", True, "")]
    assert_invalid_outputs(unknown_section, "unknown section")


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

    test_result_registry()

    print("test_json_compliance_evaluator: all tests passed")


if __name__ == "__main__":
    main()
