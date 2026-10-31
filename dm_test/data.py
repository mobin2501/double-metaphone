"""Load and validate the name list and labeled test cases.

Validation collects every problem before failing so a generated CSV can be
fixed in one pass. Problems fall into two groups:

- integrity errors (bad lengths, missing targets, duplicates, ...) are always fatal;
- distribution errors (per-length counts, positive/negative split) are fatal unless
  ``allow_uneven`` is set, in which case they are reported as warnings.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

POSITIVE = "positive"
NEGATIVE = "negative"

ORIGINS = frozenset({
    "anglo", "germanic", "slavic", "jewish", "hispanic", "italian",
    "french", "arabic", "east_asian", "south_asian", "other",
})
POSITIVE_VARIANTS = frozenset({"spelling_variant", "transliteration", "phonetic_respelling"})
NEGATIVE_VARIANTS = frozenset({"look_alike", "unrelated"})

NAME_COLUMNS = ("id", "name", "origin")
CASE_COLUMNS = ("case_id", "query", "length", "case_type", "expected_match", "variant_type", "rationale")

# ASCII words joined by single spaces or hyphens, e.g. "Li", "Garcia-Lopez", "Van der Berg".
NAME_PATTERN = re.compile(r"^[A-Za-z]+(?:[ -][A-Za-z]+)*$")
CASE_ID_PATTERN = re.compile(r"^L(\d{2})-\d{2}$")


@dataclass(frozen=True)
class DistributionSpec:
    """Expected shape of the dataset; the defaults describe the real test."""

    min_length: int = 2
    max_length: int = 21
    names_per_length: int = 50
    cases_per_length: int = 10
    positives_per_length: int = 7

    @property
    def lengths(self) -> range:
        return range(self.min_length, self.max_length + 1)


DEFAULT_SPEC = DistributionSpec()


@dataclass(frozen=True)
class Name:
    id: int
    name: str
    origin: str


@dataclass(frozen=True)
class Case:
    case_id: str
    query: str
    length: int
    case_type: str
    expected_match: str | None
    variant_type: str
    rationale: str


class DataValidationError(Exception):
    """Raised with every problem found in a data file."""

    def __init__(self, source: str, errors: list[str]):
        self.source = source
        self.errors = errors
        lines = "\n".join(f"  - {e}" for e in errors)
        super().__init__(f"{source}: {len(errors)} problem(s)\n{lines}")


@dataclass
class _Findings:
    allow_uneven: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def distribution(self, message: str) -> None:
        (self.warnings if self.allow_uneven else self.errors).append(message)

    def raise_if_errors(self, source: str) -> list[str]:
        if self.errors:
            raise DataValidationError(source, self.errors)
        return self.warnings


def _read_rows(path: Path, columns: tuple[str, ...]) -> list[tuple[int, dict[str, str]]]:
    """Return (line number, stripped row) pairs, skipping blank lines."""
    # utf-8-sig tolerates the BOM that spreadsheet exports often add.
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in reader.fieldnames or []]
        missing = [c for c in columns if c not in header]
        if missing:
            raise DataValidationError(str(path), [f"missing column(s): {', '.join(missing)}"])
        reader.fieldnames = header
        rows = []
        for row in reader:
            values = {k: (v or "").strip() for k, v in row.items() if k is not None}
            if any(values.values()):
                rows.append((reader.line_num, values))
        return rows


def load_names(path: str | Path) -> list[Name]:
    path = Path(path)
    errors: list[str] = []
    names = []
    for line, row in _read_rows(path, NAME_COLUMNS):
        try:
            names.append(Name(id=int(row["id"]), name=row["name"], origin=row["origin"]))
        except ValueError:
            errors.append(f"line {line}: id {row['id']!r} is not an integer")
    if errors:
        raise DataValidationError(str(path), errors)
    return names


def load_cases(path: str | Path) -> list[Case]:
    path = Path(path)
    errors: list[str] = []
    cases = []
    for line, row in _read_rows(path, CASE_COLUMNS):
        try:
            length = int(row["length"])
        except ValueError:
            errors.append(f"line {line}: length {row['length']!r} is not an integer")
            continue
        cases.append(Case(
            case_id=row["case_id"],
            query=row["query"],
            length=length,
            case_type=row["case_type"].lower(),
            expected_match=row["expected_match"] or None,
            variant_type=row["variant_type"].lower(),
            rationale=row["rationale"],
        ))
    if errors:
        raise DataValidationError(str(path), errors)
    return cases


def _duplicates(values) -> list:
    return sorted(v for v, n in Counter(values).items() if n > 1)


def validate_names(
    names: list[Name],
    spec: DistributionSpec = DEFAULT_SPEC,
    allow_uneven: bool = False,
) -> list[str]:
    """Raise DataValidationError on problems; return warnings otherwise."""
    found = _Findings(allow_uneven)

    for dup in _duplicates(n.id for n in names):
        found.errors.append(f"duplicate id {dup}")
    for dup in _duplicates(n.name.casefold() for n in names):
        found.errors.append(f"duplicate name {dup!r} (case-insensitive)")
    for n in names:
        if not NAME_PATTERN.match(n.name):
            found.errors.append(f"id {n.id}: name {n.name!r} must be ASCII letters with single spaces/hyphens")
        if n.origin not in ORIGINS:
            found.errors.append(f"id {n.id}: unknown origin {n.origin!r}")
        if len(n.name) not in spec.lengths:
            found.distribution(f"id {n.id}: {n.name!r} has length {len(n.name)}, outside {spec.min_length}..{spec.max_length}")

    expected_total = spec.names_per_length * len(spec.lengths)
    if len(names) != expected_total:
        found.distribution(f"expected {expected_total} names, found {len(names)}")
    per_length = Counter(len(n.name) for n in names)
    for length in spec.lengths:
        if per_length[length] != spec.names_per_length:
            found.distribution(f"length {length}: expected {spec.names_per_length} names, found {per_length[length]}")

    return found.raise_if_errors("names")


def validate_cases(
    cases: list[Case],
    names: list[Name],
    spec: DistributionSpec = DEFAULT_SPEC,
    allow_uneven: bool = False,
) -> list[str]:
    """Raise DataValidationError on problems; return warnings otherwise."""
    found = _Findings(allow_uneven)
    exact_names = {n.name for n in names}
    folded_names = {n.name.casefold(): n.name for n in names}

    for dup in _duplicates(c.case_id for c in cases):
        found.errors.append(f"duplicate case_id {dup!r}")
    # A repeated query would be scored twice and skew the metrics.
    for dup in _duplicates(c.query.casefold() for c in cases):
        found.errors.append(f"duplicate query {dup!r} (case-insensitive)")

    for c in cases:
        where = f"case {c.case_id or '<no id>'} ({c.query!r})"
        id_match = CASE_ID_PATTERN.match(c.case_id)
        if not id_match:
            found.warnings.append(f"{where}: case_id should look like L07-03")
        elif int(id_match.group(1)) != len(c.query):
            found.warnings.append(f"{where}: case_id prefix does not match query length {len(c.query)}")

        if not NAME_PATTERN.match(c.query):
            found.errors.append(f"{where}: query must be ASCII letters with single spaces/hyphens")
        if c.length != len(c.query):
            found.errors.append(f"{where}: length column says {c.length}, actual length is {len(c.query)}")
        if c.query.casefold() in folded_names:
            found.errors.append(f"{where}: query is already in the name list")
        if len(c.query) not in spec.lengths:
            found.distribution(f"{where}: length {len(c.query)} outside {spec.min_length}..{spec.max_length}")

        if c.case_type == POSITIVE:
            if c.variant_type not in POSITIVE_VARIANTS:
                found.errors.append(f"{where}: variant_type {c.variant_type!r} not valid for a positive case")
            if c.expected_match is None:
                found.errors.append(f"{where}: positive case has no expected_match")
            elif c.expected_match not in exact_names:
                hint = folded_names.get(c.expected_match.casefold())
                suffix = f" (did you mean {hint!r}?)" if hint else ""
                found.errors.append(f"{where}: expected_match {c.expected_match!r} is not in the name list{suffix}")
        elif c.case_type == NEGATIVE:
            if c.variant_type not in NEGATIVE_VARIANTS:
                found.errors.append(f"{where}: variant_type {c.variant_type!r} not valid for a negative case")
            if c.expected_match is not None:
                found.errors.append(f"{where}: negative case must have an empty expected_match")
        else:
            found.errors.append(f"{where}: case_type {c.case_type!r} must be positive or negative")

    targets = (c.expected_match for c in cases if c.case_type == POSITIVE and c.expected_match)
    for dup in _duplicates(targets):
        found.warnings.append(f"expected_match {dup!r} is the target of more than one case")

    expected_total = spec.cases_per_length * len(spec.lengths)
    if len(cases) != expected_total:
        found.distribution(f"expected {expected_total} cases, found {len(cases)}")
    expected_negatives = spec.cases_per_length - spec.positives_per_length
    for length in spec.lengths:
        bucket = [c for c in cases if len(c.query) == length]
        positives = sum(c.case_type == POSITIVE for c in bucket)
        negatives = sum(c.case_type == NEGATIVE for c in bucket)
        if (positives, negatives) != (spec.positives_per_length, expected_negatives):
            found.distribution(
                f"length {length}: expected {spec.positives_per_length} positive / {expected_negatives} negative, "
                f"found {positives} / {negatives}"
            )

    return found.raise_if_errors("test cases")
