"""Tests for the benchmark data generator (bench/gen.py).

REPORT.md's formulas assume the generated data really has the shape they claim:
unique ids so nothing collapses under set semantics, and a match rate that means
what it says. `k=0` in particular must produce no matches at all, which is the
Q5 baseline separating comparison cost from output-construction cost.
"""

from __future__ import annotations

from collections import Counter

import pytest
from gen import generate


def join_rows(r: list[tuple[int, int]], s: list[tuple[int, int]]) -> int:
    """Count R.b = S.b pairs.  R rows are (a, b), S rows are (b, c)."""
    s_keys = Counter(b for b, _c in s)
    return sum(s_keys[b] for _a, b in r)


@pytest.mark.parametrize("k", [0, 1])
def test_ids_are_unique(k: int) -> None:
    """Distinct a and c mean no tuple collapses, so the real n is the requested n."""
    r, s = generate(2000, 2000, k, seed=42)
    assert len(r) == len(s) == 2000
    assert len({a for a, _b in r}) == 2000
    assert len({c for _b, c in s}) == 2000


def test_match_rate_zero_produces_no_matches() -> None:
    """k=0 must emit nothing: the b domains are drawn disjointly."""
    r, s = generate(2000, 2000, 0, seed=42)
    assert join_rows(r, s) == 0


@pytest.mark.parametrize("k", [1, 1000])
def test_match_rate_gives_about_k_matches_per_tuple(k: int) -> None:
    """Output is about n*k rows, which is what the Q5 table reports."""
    n = 2000
    r, s = generate(n, n, k, seed=42)
    rows = join_rows(r, s)
    assert rows == pytest.approx(n * k, rel=0.10), f"k={k}: {rows} rows, expected ~{n * k}"
