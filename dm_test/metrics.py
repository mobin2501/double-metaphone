"""Score test cases against a matcher and summarize accuracy.

Outcomes are case-level:

- TP: positive case whose expected match is among the candidates
- FN: positive case whose expected match is missing
- FP: negative case with at least one candidate
- TN: negative case with no candidates

Extra candidates on positive cases are not counted as FP; they show up in
``mean_candidates`` and ``candidate_precision`` instead. Metrics with a zero
denominator are ``None`` (rendered as n/a), never 0.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Protocol

from dm_test.data import POSITIVE, Case

TP, FN, FP, TN = "TP", "FN", "FP", "TN"


class Matcher(Protocol):
    def match(self, query: str) -> list[str]: ...


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    query: str
    length: int
    case_type: str
    variant_type: str
    expected_match: str | None
    outcome: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class Summary:
    n: int
    tp: int
    fn: int
    fp: int
    tn: int
    precision: float | None
    recall: float | None
    f1: float | None
    accuracy: float | None
    specificity: float | None
    mean_candidates: float | None
    candidate_precision: float | None


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _outcome(case: Case, candidates: list[str]) -> str:
    if case.case_type == POSITIVE:
        return TP if case.expected_match in candidates else FN
    return FP if candidates else TN


def evaluate_cases(cases: list[Case], matcher: Matcher) -> list[CaseResult]:
    results = []
    for case in cases:
        candidates = matcher.match(case.query)
        results.append(CaseResult(
            case_id=case.case_id,
            query=case.query,
            length=case.length,
            case_type=case.case_type,
            variant_type=case.variant_type,
            expected_match=case.expected_match,
            outcome=_outcome(case, candidates),
            candidates=tuple(candidates),
        ))
    return results


def summarize_overall(results: list[CaseResult]) -> Summary:
    counts = {k: sum(r.outcome == k for r in results) for k in (TP, FN, FP, TN)}
    tp, fn, fp, tn = counts[TP], counts[FN], counts[FP], counts[TN]
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = (
        _ratio(2 * precision * recall, precision + recall)
        if precision is not None and recall is not None
        else None
    )
    hits = [r for r in results if r.outcome == TP]
    return Summary(
        n=len(results),
        tp=tp,
        fn=fn,
        fp=fp,
        tn=tn,
        precision=precision,
        recall=recall,
        f1=f1,
        accuracy=_ratio(tp + tn, len(results)),
        specificity=_ratio(tn, tn + fp),
        mean_candidates=_ratio(sum(len(r.candidates) for r in results), len(results)),
        candidate_precision=_ratio(sum(1 / len(r.candidates) for r in hits), len(hits)),
    )


def _summarize_by(results: list[CaseResult], key: Callable[[CaseResult], Hashable]) -> dict:
    groups: dict = defaultdict(list)
    for r in results:
        groups[key(r)].append(r)
    return {k: summarize_overall(groups[k]) for k in sorted(groups)}


def summarize_by_length(results: list[CaseResult]) -> dict[int, Summary]:
    return _summarize_by(results, lambda r: r.length)


def summarize_by_variant(results: list[CaseResult]) -> dict[str, Summary]:
    return _summarize_by(results, lambda r: r.variant_type)
