"""End-to-end run on data/sample/ with real abydos.

Outcomes are pinned per case so a library upgrade that changes matching
behaviour fails here instead of silently shifting the report.
"""

import csv
import json
from pathlib import Path

import pytest

from dm_test.cli import main

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"

DEFAULT_OUTCOMES = {
    "L02-01": "TP", "L02-02": "TN", "L03-01": "TP", "L03-02": "TP", "L03-03": "TN",
    "L05-01": "TP", "L05-02": "TP", "L05-03": "TP", "L06-01": "TN", "L07-01": "TP",
    "L07-02": "TN", "L08-01": "TP", "L08-02": "FN", "L08-03": "TN", "L09-01": "TP",
    "L09-02": "TP", "L09-03": "FP", "L10-01": "FN", "L10-02": "TP", "L12-01": "TP",
    "L15-01": "TP", "L19-01": "TN", "L19-02": "TP", "L21-01": "TP",
}


def run_sample(out: Path, *extra: str) -> list[dict]:
    args = ["--names", str(SAMPLE / "names.csv"), "--cases", str(SAMPLE / "test_cases.csv"),
            "--out", str(out), "--allow-uneven", *extra]
    assert main(args) == 0
    with open(out / "artifact 1.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def default_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("default")
    return out, run_sample(out)


def test_all_outputs_written(default_run):
    out, _ = default_run
    for name in ("artifact 1.csv", "artifact 2.json", "artifact 3.pdf", "artifact 4.png", "artifact 5.png"):
        assert (out / name).stat().st_size > 0, name
    assert (out / "artifact 3.pdf").read_bytes().startswith(b"%PDF")


def test_default_outcomes_are_pinned(default_run):
    _, rows = default_run
    assert {r["case_id"]: r["outcome"] for r in rows} == DEFAULT_OUTCOMES


def test_compound_names_match_as_a_whole(default_run):
    _, rows = default_run
    by_id = {r["case_id"]: r for r in rows}
    assert by_id["L19-01"]["candidates"] == ""
    assert by_id["L12-01"]["candidates"] == "Garcia-Lopez"
    assert by_id["L21-01"]["candidates"] == "Vladislav Tchaikovsky"


def test_summary_totals(default_run):
    out, _ = default_run
    overall = json.loads((out / "artifact 2.json").read_text(encoding="utf-8"))["overall"]
    assert (overall["tp"], overall["fn"], overall["fp"], overall["tn"]) == (15, 2, 1, 6)


def test_max_length_matches_on_code_prefix(tmp_path):
    rows = {r["case_id"]: r for r in run_sample(tmp_path, "--max-length", "4")}
    # "Hernandez Rodriguez" and "Hernandez Cruz" both start HRNN.
    assert rows["L19-01"]["outcome"] == "FP"
    assert rows["L19-01"]["candidates"] == "Hernandez Cruz"
    assert rows["L10-01"]["outcome"] == "TP"
