"""Command-line runner: validate data, score every case, print and save results."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from dm_test.data import (
    NEGATIVE,
    POSITIVE,
    DataValidationError,
    load_cases,
    load_names,
    validate_cases,
    validate_names,
)
from dm_test.matcher import NO_MAX_LENGTH, DMMatcher, check_max_length
from dm_test.metrics import (
    CaseResult,
    Summary,
    evaluate_cases,
    summarize_by_length,
    summarize_by_variant,
    summarize_overall,
)
from dm_test.report import build_report

EXIT_DATA_ERROR = 2

RESULTS_FILE = "artifact 1.csv"
SUMMARY_FILE = "artifact 2.json"

RESULT_COLUMNS = (
    "case_id", "query", "length", "case_type", "variant_type",
    "expected_match", "outcome", "candidate_count", "candidates",
)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure Double Metaphone phonetic matching accuracy.")
    parser.add_argument("--names", type=Path, default=Path("data/input 1.csv"), help="name list CSV")
    parser.add_argument("--cases", type=Path, default=Path("data/input 2.csv"), help="test cases CSV")
    parser.add_argument("--out", type=Path, default=Path("results"), help="output directory")
    parser.add_argument("--max-length", type=int, default=NO_MAX_LENGTH,
                        help="truncate codes to this many characters (-1, the default, means no limit; minimum 4)")
    parser.add_argument("--allow-uneven", action="store_true",
                        help="report per-length count mismatches as warnings instead of errors")
    args = parser.parse_args(argv)
    try:
        check_max_length(args.max_length)
    except ValueError as e:
        parser.error(str(e))
    return args


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _summary_row(label: str, s: Summary) -> list[str]:
    return [
        label, str(s.n), str(s.tp), str(s.fn), str(s.fp), str(s.tn),
        _pct(s.recall), _pct(s.specificity), _pct(s.precision), _pct(s.f1),
        _num(s.mean_candidates),
    ]


def _table(header: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
    # Label column left-aligned, numbers right-aligned.
    lines = [
        "  ".join(cell.ljust(w) if i == 0 else cell.rjust(w) for i, (cell, w) in enumerate(zip(row, widths)))
        for row in [header, ["-" * w for w in widths], *rows]
    ]
    return "\n".join(lines)


SUMMARY_HEADER = ["", "N", "TP", "FN", "FP", "TN", "Recall", "Spec", "Prec", "F1", "Avg cand"]


def format_report(config: dict, overall: Summary, by_length: dict, by_variant: dict) -> str:
    config_line = f"max_length={config['max_length']}"
    headline = (
        f"Overall: recall {_pct(overall.recall)}, precision {_pct(overall.precision)}, "
        f"F1 {_pct(overall.f1)}, accuracy {_pct(overall.accuracy)}, "
        f"specificity {_pct(overall.specificity)}, "
        f"candidate precision {_pct(overall.candidate_precision)}"
    )
    length_rows = [_summary_row(str(k), s) for k, s in by_length.items()]
    variant_rows = [_summary_row(k, s) for k, s in by_variant.items()]
    return "\n\n".join([
        f"Double Metaphone accuracy test ({config_line})",
        headline,
        "By query length\n" + _table(["Len", *SUMMARY_HEADER[1:]], [*length_rows, _summary_row("All", overall)]),
        "By variant type\n" + _table(["Variant", *SUMMARY_HEADER[1:]], variant_rows),
    ])


def write_results_csv(path: Path, results: list[CaseResult]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(RESULT_COLUMNS)
        for r in results:
            writer.writerow([
                r.case_id, r.query, r.length, r.case_type, r.variant_type,
                r.expected_match or "", r.outcome, len(r.candidates), "|".join(r.candidates),
            ])


def build_summary(config: dict, dataset: dict, warnings: list[str],
                  overall: Summary, by_length: dict, by_variant: dict) -> dict:
    return {
        "config": config,
        "dataset": dataset,
        "warnings": warnings,
        "overall": asdict(overall),
        # JSON keys must be strings.
        "by_length": {str(k): asdict(s) for k, s in by_length.items()},
        "by_variant": {k: asdict(s) for k, s in by_variant.items()},
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        names = load_names(args.names)
        cases = load_cases(args.cases)
        warnings = validate_names(names, allow_uneven=args.allow_uneven)
        warnings += validate_cases(cases, names, allow_uneven=args.allow_uneven)
    except FileNotFoundError as e:
        print(f"error: file not found: {e.filename}", file=sys.stderr)
        return EXIT_DATA_ERROR
    except DataValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        if not args.allow_uneven:
            print("hint: --allow-uneven downgrades per-length count mismatches to warnings", file=sys.stderr)
        return EXIT_DATA_ERROR

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    matcher = DMMatcher(max_length=args.max_length)
    matcher.build_index(n.name for n in names)
    results = evaluate_cases(cases, matcher)

    overall = summarize_overall(results)
    by_length = summarize_by_length(results)
    by_variant = summarize_by_variant(results)

    config = {
        "max_length": args.max_length,
        "allow_uneven": args.allow_uneven,
        "names_file": str(args.names),
        "cases_file": str(args.cases),
        "abydos_version": version("abydos"),
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    dataset = {
        "names": len(names),
        "cases": len(cases),
        "positives": sum(c.case_type == POSITIVE for c in cases),
        "negatives": sum(c.case_type == NEGATIVE for c in cases),
    }

    print(format_report(config, overall, by_length, by_variant))

    args.out.mkdir(parents=True, exist_ok=True)
    write_results_csv(args.out / RESULTS_FILE, results)
    summary = build_summary(config, dataset, warnings, overall, by_length, by_variant)
    (args.out / SUMMARY_FILE).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    report = build_report(args.out, summary, results, matcher.encode)
    print(f"\nWrote {args.out / RESULTS_FILE}, {args.out / SUMMARY_FILE} and {report}")
    return 0
