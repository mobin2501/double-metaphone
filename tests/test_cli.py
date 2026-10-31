import csv
import json

import pytest

from dm_test.cli import EXIT_DATA_ERROR, main

NAMES_CSV = """id,name,origin
1,Li,east_asian
2,Schmidt,germanic
3,Rodriguez,hispanic
"""

CASES_CSV = """case_id,query,length,case_type,expected_match,variant_type,rationale
L05-01,Shmit,5,positive,Schmidt,phonetic_respelling,same sound
L03-01,Pax,3,negative,,unrelated,no similar name
"""


@pytest.fixture
def data_files(tmp_path):
    names = tmp_path / "names.csv"
    cases = tmp_path / "cases.csv"
    names.write_text(NAMES_CSV, encoding="utf-8")
    cases.write_text(CASES_CSV, encoding="utf-8")
    return names, cases, tmp_path / "out"


def run(names, cases, out, *extra):
    return main(["--names", str(names), "--cases", str(cases), "--out", str(out), *extra])


def test_run_writes_results_and_summary(data_files, capsys):
    names, cases, out = data_files
    assert run(names, cases, out, "--allow-uneven") == 0

    stdout = capsys.readouterr().out
    assert "Overall: recall 100.0%" in stdout
    assert "By query length" in stdout
    assert "By variant type" in stdout

    with open(out / "artifact 1.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [(r["case_id"], r["outcome"], r["candidates"]) for r in rows] == [
        ("L05-01", "TP", "Schmidt"),
        ("L03-01", "TN", ""),
    ]

    summary = json.loads((out / "artifact 2.json").read_text(encoding="utf-8"))
    assert summary["config"]["max_length"] == -1
    assert summary["config"]["abydos_version"] == "0.5.0"
    assert summary["dataset"] == {"names": 3, "cases": 2, "positives": 1, "negatives": 1}
    assert summary["overall"]["tp"] == 1 and summary["overall"]["tn"] == 1
    assert set(summary["by_length"]) == {"3", "5"}
    assert summary["warnings"]
    assert (out / "artifact 3.pdf").read_bytes().startswith(b"%PDF")


def test_uneven_data_fails_without_flag(data_files, capsys):
    names, cases, out = data_files
    assert run(names, cases, out) == EXIT_DATA_ERROR
    stderr = capsys.readouterr().err
    assert "expected 1000 names, found 3" in stderr
    assert "--allow-uneven" in stderr
    assert not out.exists()


def test_integrity_error_fails_even_with_flag(data_files, capsys):
    names, cases, out = data_files
    cases.write_text(CASES_CSV.replace("Shmit,5", "Shmit,6"), encoding="utf-8")
    assert run(names, cases, out, "--allow-uneven") == EXIT_DATA_ERROR
    assert "actual length is 5" in capsys.readouterr().err


def test_missing_file_fails(data_files, capsys):
    _, cases, out = data_files
    assert run(out / "nope.csv", cases, out) == EXIT_DATA_ERROR
    assert "file not found" in capsys.readouterr().err


def test_max_length_is_recorded(data_files):
    names, cases, out = data_files
    assert run(names, cases, out, "--allow-uneven", "--max-length", "6") == 0
    config = json.loads((out / "artifact 2.json").read_text(encoding="utf-8"))["config"]
    assert config["max_length"] == 6


def test_max_length_below_four_is_rejected(data_files, capsys):
    names, cases, out = data_files
    with pytest.raises(SystemExit) as exc:
        run(names, cases, out, "--allow-uneven", "--max-length", "3")
    assert exc.value.code == 2
    assert "at least 4" in capsys.readouterr().err
    assert not out.exists()
