import pytest

from dm_test.matcher import DMMatcher

NAMES = ["Li", "Kim", "Schmidt", "Rodriguez", "Garcia-Lopez", "Berg"]


@pytest.fixture(scope="module")
def matcher():
    m = DMMatcher()
    m.build_index(NAMES)
    return m


def test_encode_returns_primary_and_alternate(matcher):
    assert matcher.encode("Schmidt") == frozenset({"XMT", "SMT"})


def test_encode_drops_empty_alternate(matcher):
    assert matcher.encode("Kim") == frozenset({"KM"})


def test_encode_is_cached(matcher):
    assert matcher.encode("Schmidt") is matcher.encode("Schmidt")


def test_phonetic_variant_matches(matcher):
    assert matcher.match("Shmit") == ["Schmidt"]


def test_unrelated_query_matches_nothing(matcher):
    assert matcher.match("Pax") == []


def test_distinct_short_names_do_not_match_each_other(matcher):
    assert "Kim" not in matcher.match("Li")


def test_matches_follow_list_order():
    m = DMMatcher()
    m.build_index(["Smith", "Schmidt", "Schmitt"])
    # Smith's alternate (XMT) is the primary of the other two.
    assert m.match("Shmit") == ["Smith", "Schmidt", "Schmitt"]


def test_whole_name_encoding_ignores_separators(matcher):
    assert matcher.encode("Garcia Lopes") == matcher.encode("Garcia-Lopez") == frozenset({"KRSLPS", "KRXLPS"})
    assert matcher.match("Garcia Lopes") == ["Garcia-Lopez"]


def test_single_word_does_not_match_compound(matcher):
    assert "Rodriguez" not in matcher.match("Hernandez Rodriguez")


def test_codes_are_not_truncated_by_default(matcher):
    assert matcher.encode("Christopher") == frozenset({"KRSTFR"})


def test_max_length_truncates_codes():
    m = DMMatcher(max_length=4)
    assert m.encode("Christopher") == frozenset({"KRST"})
    m.build_index(["Rodriguez-Lopez"])
    assert m.match("Rodriguez") == ["Rodriguez-Lopez"]


@pytest.mark.parametrize("max_length", [0, 3, -2])
def test_max_length_below_four_rejected(max_length):
    with pytest.raises(ValueError, match="max_length"):
        DMMatcher(max_length=max_length)


def test_match_before_index_raises():
    with pytest.raises(RuntimeError, match="build_index"):
        DMMatcher().match("Li")


def test_duplicate_names_indexed_once():
    m = DMMatcher()
    m.build_index(["Schmidt", "Schmidt"])
    assert m.match("Shmit") == ["Schmidt"]
