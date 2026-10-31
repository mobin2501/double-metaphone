import dataclasses

import pytest

from dm_test.data import (
    Case,
    DataValidationError,
    DistributionSpec,
    Name,
    load_cases,
    load_names,
    validate_cases,
    validate_names,
)

# Lengths 2..3, 2 names and 2 cases (1 positive / 1 negative) per length.
SPEC = DistributionSpec(min_length=2, max_length=3, names_per_length=2, cases_per_length=2, positives_per_length=1)

NAMES = [
    Name(1, "Li", "east_asian"),
    Name(2, "Wu", "east_asian"),
    Name(3, "Lee", "anglo"),
    Name(4, "Kim", "east_asian"),
]

CASES = [
    Case("L02-01", "Ly", 2, "positive", "Li", "transliteration", "same sound"),
    Case("L02-02", "Oz", 2, "negative", None, "unrelated", "no similar name"),
    Case("L03-01", "Woo", 3, "positive", "Wu", "transliteration", "same sound"),
    Case("L03-02", "Pax", 3, "negative", None, "unrelated", "no similar name"),
]


def errors_of(excinfo) -> str:
    return "\n".join(excinfo.value.errors)


def replace_case(index: int, **changes) -> list[Case]:
    cases = list(CASES)
    cases[index] = dataclasses.replace(cases[index], **changes)
    return cases


# --- loading ---------------------------------------------------------------

def test_load_names_handles_bom_whitespace_and_blank_lines(tmp_path):
    path = tmp_path / "names.csv"
    path.write_text("﻿id, name ,origin\n1, Li ,east_asian\n\n2,Wu,east_asian\n", encoding="utf-8")
    assert load_names(path) == [Name(1, "Li", "east_asian"), Name(2, "Wu", "east_asian")]


def test_load_names_reports_missing_columns(tmp_path):
    path = tmp_path / "names.csv"
    path.write_text("id,name\n1,Li\n", encoding="utf-8")
    with pytest.raises(DataValidationError, match="missing column"):
        load_names(path)


def test_load_names_reports_non_integer_id(tmp_path):
    path = tmp_path / "names.csv"
    path.write_text("id,name,origin\nx,Li,east_asian\n", encoding="utf-8")
    with pytest.raises(DataValidationError, match="not an integer"):
        load_names(path)


def test_load_cases_normalizes_fields(tmp_path):
    path = tmp_path / "cases.csv"
    path.write_text(
        "case_id,query,length,case_type,expected_match,variant_type,rationale\n"
        "L02-02,Oz,2,Negative,,Unrelated,no match\n",
        encoding="utf-8",
    )
    assert load_cases(path) == [Case("L02-02", "Oz", 2, "negative", None, "unrelated", "no match")]


# --- names -----------------------------------------------------------------

def test_valid_names_pass():
    assert validate_names(NAMES, SPEC) == []


def test_duplicate_names_are_case_insensitive():
    with pytest.raises(DataValidationError) as excinfo:
        validate_names(NAMES + [Name(5, "LI", "east_asian")], SPEC, allow_uneven=True)
    assert "duplicate name 'li'" in errors_of(excinfo)


def test_invalid_name_characters_and_origin_are_errors():
    names = NAMES[:-1] + [Name(4, "O'K", "martian")]
    with pytest.raises(DataValidationError) as excinfo:
        validate_names(names, SPEC)
    text = errors_of(excinfo)
    assert "ASCII letters" in text
    assert "unknown origin 'martian'" in text


def test_uneven_name_distribution_is_error_by_default():
    with pytest.raises(DataValidationError) as excinfo:
        validate_names(NAMES[:-1], SPEC)
    assert "length 3: expected 2 names, found 1" in errors_of(excinfo)


def test_uneven_name_distribution_is_warning_when_allowed():
    warnings = validate_names(NAMES[:-1], SPEC, allow_uneven=True)
    assert any("length 3: expected 2 names, found 1" in w for w in warnings)


def test_all_problems_are_reported_together():
    names = [Name(1, "Li", "x"), Name(1, "Li", "y")]
    with pytest.raises(DataValidationError) as excinfo:
        validate_names(names, SPEC)
    # duplicate id, duplicate name, 2 bad origins, total count, length-3 count
    assert len(excinfo.value.errors) == 6


# --- cases -----------------------------------------------------------------

def test_valid_cases_pass():
    assert validate_cases(CASES, NAMES, SPEC) == []


def test_length_column_must_match_query():
    with pytest.raises(DataValidationError) as excinfo:
        validate_cases(replace_case(0, length=3), NAMES, SPEC)
    assert "length column says 3, actual length is 2" in errors_of(excinfo)


def test_positive_target_must_exist_exactly():
    with pytest.raises(DataValidationError) as excinfo:
        validate_cases(replace_case(0, expected_match="li"), NAMES, SPEC)
    assert "did you mean 'Li'?" in errors_of(excinfo)


def test_positive_without_target_is_error():
    with pytest.raises(DataValidationError, match="no expected_match"):
        validate_cases(replace_case(0, expected_match=None), NAMES, SPEC)


def test_negative_with_target_is_error():
    with pytest.raises(DataValidationError, match="must have an empty expected_match"):
        validate_cases(replace_case(1, expected_match="Li"), NAMES, SPEC)


def test_query_in_name_list_is_error():
    with pytest.raises(DataValidationError, match="already in the name list"):
        validate_cases(replace_case(0, query="LI"), NAMES, SPEC)


def test_duplicate_queries_are_case_insensitive():
    with pytest.raises(DataValidationError) as excinfo:
        validate_cases(replace_case(1, query="LY"), NAMES, SPEC, allow_uneven=True)
    assert "duplicate query 'ly'" in errors_of(excinfo)


def test_variant_type_must_fit_case_type():
    with pytest.raises(DataValidationError) as excinfo:
        validate_cases(replace_case(1, variant_type="transliteration"), NAMES, SPEC)
    assert "not valid for a negative case" in errors_of(excinfo)


def test_unknown_case_type_is_error():
    with pytest.raises(DataValidationError, match="must be positive or negative"):
        validate_cases(replace_case(0, case_type="maybe"), NAMES, SPEC, allow_uneven=True)


def test_uneven_split_is_error_by_default_and_warning_when_allowed():
    cases = replace_case(1, case_type="positive", expected_match="Lee", variant_type="spelling_variant")
    with pytest.raises(DataValidationError) as excinfo:
        validate_cases(cases, NAMES, SPEC)
    assert "length 2: expected 1 positive / 1 negative, found 2 / 0" in errors_of(excinfo)
    warnings = validate_cases(cases, NAMES, SPEC, allow_uneven=True)
    assert any("found 2 / 0" in w for w in warnings)


def test_integrity_errors_stay_fatal_when_uneven_allowed():
    with pytest.raises(DataValidationError, match="actual length"):
        validate_cases(replace_case(0, length=9), NAMES, SPEC, allow_uneven=True)


def test_reused_target_and_bad_case_id_are_warnings():
    cases = replace_case(2, expected_match="Li", case_id="case3")
    warnings = validate_cases(cases, NAMES, SPEC)
    assert any("'Li' is the target of more than one case" in w for w in warnings)
    assert any("case_id should look like" in w for w in warnings)
