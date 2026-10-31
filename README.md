# Double Metaphone Accuracy Test

Measures the accuracy of Double Metaphone phonetic matching (via
[abydos](https://github.com/chrislit/abydos)) against a 1000-name list using
200 labeled queries — 10 per query length 2..21 (7 positive / 3 negative each).

Each name gets a primary code and, when the algorithm finds a second plausible
pronunciation, an alternate code. A query matches a list name when their code
sets share at least one code. A positive case passes when its expected name is
among the returned candidates; a negative case passes only when nothing is
returned.

## Project layout

| Path | What it is |
|---|---|
| `run_test.py` | Entry point (wraps `dm_test/cli.py`) |
| `dm_test/` | Data validation, matcher, metrics, PDF report, charts |
| `data/input 1.csv` | The 1000-name reference list (50 per length 2..21) |
| `data/input 2.csv` | The 200 labeled test queries |
| `data/sample/` | Small fixture for a quick trial run |
| `tests/` | pytest suite, including an end-to-end run on the sample |
| `results/` | Generated output (git-ignored) |

## 1. Setup

Requires Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Run the test

The dataset is already in `data/`, so a plain run needs no arguments:

```bash
python run_test.py
```

This validates both CSVs, runs every query, prints the summary tables (overall,
by length, by variant type) and writes:

| File | Contents |
|---|---|
| `results/artifact 1.csv` | One row per case: outcome (TP/FN/FP/TN) and candidates returned |
| `results/artifact 2.json` | All metrics plus the run configuration |
| `results/artifact 3.pdf` | Full report: metrics, charts, every miss and false match |
| `results/artifact 4.png` | Chart: recall and false-positive rate by query length |
| `results/artifact 5.png` | Chart: average candidates returned by query length |

### Options

| Flag | Default | Effect |
|---|---|---|
| `--names PATH` | `data/input 1.csv` | Name list CSV |
| `--cases PATH` | `data/input 2.csv` | Test cases CSV |
| `--out DIR` | `results` | Output directory |
| `--max-length N` | `-1` | Truncate codes to N characters (minimum 4); `-1` is the library default and keeps full-length codes |
| `--allow-uneven` | off | Report per-length count mismatches as warnings instead of errors |

Names are encoded as one string. Spaces and hyphens add no code, so
"Garcia Lopes" matches "Garcia-Lopez", but "Hernandez Rodriguez" does not match
"Rodriguez". With `--max-length 4`, names whose codes share the first four
characters match, so "Hernandez Rodriguez" then matches "Hernandez Cruz".

Each run overwrites its output directory. To compare settings, give each run its
own `--out`:

```bash
python run_test.py --out results/default
python run_test.py --max-length 4 --out results/max4
```

### Quick trial on the sample

`data/sample/` (40 names, 24 cases) doesn't have the full 50/10-per-length
counts, so it needs `--allow-uneven`:

```bash
python run_test.py --names data/sample/names.csv --cases data/sample/test_cases.csv \
  --out results/sample --allow-uneven
```

## 3. Run the unit tests

```bash
pytest
```

## Using a different dataset

Replace `data/input 1.csv` and `data/input 2.csv` with your own files, then run
`python run_test.py`.

Both files must use the column layout shown in `data/sample/`.

The runner checks the data before matching and lists every problem at once.
Fix the files and rerun until it passes.

- **Always fatal:**
  - a `length` value that doesn't match the name
  - duplicate names or duplicate queries
  - a query that is already in the name list
  - a positive whose `expected_match` isn't in the list
  - a negative with an `expected_match`
  - an unknown `origin` or `variant_type`
- **Fatal unless `--allow-uneven` is set:** wrong counts per length, or a
  positive/negative split other than 7/3.

## License

MIT. See [LICENSE](LICENSE).
