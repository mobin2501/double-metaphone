import pytest

from dm_test.data import Case
from dm_test.metrics import (
    evaluate_cases,
    summarize_by_length,
    summarize_by_variant,
    summarize_overall,
)


class StubMatcher:
    def __init__(self, answers: dict[str, list[str]]):
        self.answers = answers

    def match(self, query: str) -> list[str]:
        return self.answers.get(query, [])


CASES = [
    Case("L02-01", "Ly", 2, "positive", "Li", "transliteration", ""),
    Case("L02-02", "Wo", 2, "positive", "Wu", "transliteration", ""),
    Case("L03-01", "Kym", 3, "positive", "Kim", "spelling_variant", ""),
    Case("L02-03", "Oz", 2, "negative", None, "unrelated", ""),
    Case("L03-02", "Pax", 3, "negative", None, "look_alike", ""),
]

MATCHER = StubMatcher({
    "Ly": ["Li"],            # TP, 1 candidate
    "Wo": ["Lee", "Wu"],     # TP, 2 candidates
    "Kym": ["Lee"],          # FN: wrong name returned
    "Pax": ["Lee"],          # FP
})                           # "Oz" -> TN


@pytest.fixture(scope="module")
def results():
    return evaluate_cases(CASES, MATCHER)


def test_outcomes_and_candidates(results):
    assert [r.outcome for r in results] == ["TP", "TP", "FN", "TN", "FP"]
    assert results[1].candidates == ("Lee", "Wu")
    assert results[3].candidates == ()


def test_overall_summary(results):
    s = summarize_overall(results)
    assert (s.n, s.tp, s.fn, s.fp, s.tn) == (5, 2, 1, 1, 1)
    assert s.precision == pytest.approx(2 / 3)
    assert s.recall == pytest.approx(2 / 3)
    assert s.f1 == pytest.approx(2 / 3)
    assert s.accuracy == pytest.approx(3 / 5)
    assert s.specificity == pytest.approx(1 / 2)
    assert s.mean_candidates == pytest.approx(1.0)
    assert s.candidate_precision == pytest.approx(0.75)


def test_by_length(results):
    by_length = summarize_by_length(results)
    assert list(by_length) == [2, 3]
    two, three = by_length[2], by_length[3]
    assert (two.tp, two.tn, two.precision, two.recall, two.specificity) == (2, 1, 1.0, 1.0, 1.0)
    assert (three.fn, three.fp, three.precision, three.recall) == (1, 1, 0.0, 0.0)
    # Precision and recall both 0 -> F1 undefined; no hits -> candidate precision undefined.
    assert three.f1 is None
    assert three.candidate_precision is None


def test_by_variant_negative_only_groups_have_no_recall(results):
    by_variant = summarize_by_variant(results)
    assert list(by_variant) == ["look_alike", "spelling_variant", "transliteration", "unrelated"]
    assert by_variant["unrelated"].recall is None
    assert by_variant["unrelated"].precision is None
    assert by_variant["unrelated"].specificity == 1.0
    assert by_variant["look_alike"].specificity == 0.0
    assert by_variant["transliteration"].recall == 1.0
    assert by_variant["transliteration"].specificity is None


def test_empty_results_are_all_undefined():
    s = summarize_overall([])
    assert s.n == 0
    assert all(v is None for v in (s.precision, s.recall, s.f1, s.accuracy, s.specificity, s.mean_candidates))
