"""Double Metaphone matching over a fixed name list.

A query matches a list name when their Double Metaphone code sets share at
least one code. Each name has a primary code and an alternate code; the
alternate is empty when it would equal the primary, and empty codes are
never compared.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from abydos.phonetic import DoubleMetaphone

NO_MAX_LENGTH = -1  # library default: codes are not truncated
MIN_MAX_LENGTH = 4  # the library silently raises any smaller limit to 4


def check_max_length(max_length: int) -> int:
    # Smaller limits are rejected, not raised to 4, so the recorded setting is the one applied.
    if max_length != NO_MAX_LENGTH and max_length < MIN_MAX_LENGTH:
        raise ValueError(
            f"max_length must be {NO_MAX_LENGTH} (no limit) or at least {MIN_MAX_LENGTH}, got {max_length!r}"
        )
    return max_length


class DMMatcher:
    def __init__(self, max_length: int = NO_MAX_LENGTH):
        self.max_length = check_max_length(max_length)
        # The whole string is encoded as one word. Spaces and hyphens emit no
        # code, so "Garcia-Lopez" and "Garcia Lopes" get the same codes, and a
        # compound name is matched on its whole code, not word by word.
        self._encoder = DoubleMetaphone(max_length=max_length)
        self._cache: dict[str, frozenset[str]] = {}
        self._index: dict[str, list[str]] | None = None
        self._order: dict[str, int] = {}

    def encode(self, name: str) -> frozenset[str]:
        codes = self._cache.get(name)
        if codes is None:
            codes = frozenset(code for code in self._encoder.encode(name) if code)
            self._cache[name] = codes
        return codes

    def build_index(self, names: Iterable[str]) -> None:
        index: dict[str, list[str]] = defaultdict(list)
        self._order = {}
        for name in names:
            if name in self._order:
                continue
            self._order[name] = len(self._order)
            for code in self.encode(name):
                index[code].append(name)
        self._index = dict(index)

    def match(self, query: str) -> list[str]:
        """Return list names sharing a code with ``query``, in list order."""
        if self._index is None:
            raise RuntimeError("build_index() must be called before match()")
        found = {name for code in self.encode(query) for name in self._index.get(code, ())}
        return sorted(found, key=self._order.__getitem__)
