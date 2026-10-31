from dataclasses import asdict

import pytest

from dm_test.charts import CANDIDATES_CHART, RECALL_FPR_CHART
from dm_test.data import Case
from dm_test.metrics import (
    evaluate_cases,
    summarize_by_length,
    summarize_by_variant,
    summarize_overall,
)
from dm_test.report import build_report, length_ranges, noise_note, takeaway

CASES = [
    Case("L02-01", "Ly", 2, "positive", "Li", "transliteration", ""),
    Case("L02-02", "Oz", 2, "negative", None, "unrelated", ""),
    Case("L03-01", "Kym", 3, "positive", "Kim", "spelling_variant", ""),
    Case("L03-02", "Pax", 3, "negative", None, "look_alike", ""),
]


class StubMatcher:
    answers = {"Ly": ["Li"], "Kym": ["Lee"], "Pax": ["Lee", "Li"]}

    def match(self, query):
        return self.answers.get(query, [])

    def encode(self, name):
        return frozenset({name.lower()})


def make_summary(results, warnings=()):
    return {
        "config": {
            "max_length": -1,
            "abydos_version": "0.5.0", "run_at": "2026-10-22T00:00:00+00:00",
        },
        "dataset": {"names": 4, "cases": len(results), "positives": 2, "negatives": 2},
        "warnings": list(warnings),
        "overall": asdict(summarize_overall(results)),
        "by_length": {str(k): asdict(s) for k, s in summarize_by_length(results).items()},
        "by_variant": {k: asdict(s) for k, s in summarize_by_variant(results).items()},
    }


@pytest.fixture
def results():
    return evaluate_cases(CASES, StubMatcher())


def test_build_report_writes_pdf_and_charts(tmp_path, results):
    path = build_report(tmp_path, make_summary(results, ["a warning"]), results, StubMatcher().encode)
    assert path == tmp_path / "artifact 3.pdf"
    assert path.read_bytes().startswith(b"%PDF")
    for chart in (RECALL_FPR_CHART, CANDIDATES_CHART):
        assert (tmp_path / chart).read_bytes().startswith(b"\x89PNG")


def test_build_report_handles_no_failures(tmp_path):
    perfect = evaluate_cases(CASES[:2], StubMatcher())
    assert build_report(tmp_path, make_summary(perfect), perfect, StubMatcher().encode).exists()


def test_takeaway_states_counts_and_worst_lengths(results):
    text = takeaway(make_summary(results))
    assert "<b>1 of 2</b> positive queries (recall 50.0%)" in text
    assert "<b>1 of 2</b> negative queries matched" in text
    assert "Recall was lowest at length 3 (0.0%)" in text
    assert "False positives peaked at length 3 (100.0%)" in text


def test_noise_note_uses_actual_bucket_sizes(results):
    assert "Each length has 2 queries (1 positive, 1 negative)" in noise_note(make_summary(results))


def test_noise_note_falls_back_when_buckets_differ():
    uneven = evaluate_cases(CASES[:3], StubMatcher())
    assert "between 1 and 2 queries" in noise_note(make_summary(uneven))


def test_takeaway_names_every_tied_length():
    missed = Case("L02-03", "Lo", 2, "positive", "Li", "spelling_variant", "")
    tied = evaluate_cases([missed, CASES[2]], StubMatcher())
    assert "Recall was lowest at lengths 2 and 3 (0.0%)" in takeaway(make_summary(tied))


def test_length_ranges_show_gaps():
    assert length_ranges([2, 3, 4, 7, 9, 10]) == "2-4, 7, 9-10"
    assert length_ranges([]) == "n/a"
