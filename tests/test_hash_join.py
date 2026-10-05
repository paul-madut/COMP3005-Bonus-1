"""Differential tests: the hash join must agree with the nested loop.

The hash strategy (Q6) is a second implementation of an operator that already
works, and when it was wrong it returned plausible rows from the wrong buckets
rather than raising (notes/AI_WRONG.md, "hash join keyed on the wrong
coordinates"). Each case below runs one query under both strategies and compares
the results exactly, order included: both strategies emit left rows in order
with matches in right insertion order, so a strategy switch must be invisible
in the output.
"""

from __future__ import annotations

import pytest
from run_experiment import _switch_strategy

from relalg.binder import Binder, BoundJoin, BoundNode
from relalg.catalog import Catalog
from relalg.executor import execute
from relalg.operators import Row
from relalg.parser import parse

DB = """
R (a, b) = {
  1, 10
  2, 20
  3, 20
  4, 99
}
S (b, c) = {
  10, 'p'
  20, 'q'
  20, 'r'
  30, 's'
}
T (c, d) = {
  'p', 1
  'q', 2
}
Emp (EID, MgrID) = {
  1, 2
  2, 3
  3, 3
}
Empty (b, c) = {
}
"""


def catalog() -> Catalog:
    c = Catalog()
    c.load(DB)
    return c


def run(plan: BoundNode) -> tuple[list[Row], int]:
    _, rows, stats = execute(plan)
    out = list(rows)

    def comparisons(st: object) -> int:
        return getattr(st, "comparisons", 0) + sum(
            comparisons(ch) for ch in getattr(st, "children", [])
        )

    return out, comparisons(stats)


def both_ways(query: str) -> tuple[list[Row], list[Row], int, int]:
    """Run `query` nested and hashed; return (nested_rows, hash_rows, n_cmp, h_cmp).

    The binder defaults a detected equi-join to the hash strategy, so the
    nested side has to be forced back explicitly for the comparison to stay
    differential.
    """
    cat = catalog()
    nested_rows, n_cmp = run(_switch_strategy(Binder(cat).bind(parse(query)), "nested"))
    hash_rows, h_cmp = run(_switch_strategy(Binder(cat).bind(parse(query)), "hash"))
    return nested_rows, hash_rows, n_cmp, h_cmp


EQUIVALENT_QUERIES = [
    # Plain equi-join.  R and S both repeat b=20, so this is already many-to-many.
    "R join[R.b=S.b] S",
    # Equality written the other way round: _equi_keys must normalise the sides.
    "R join[S.b=R.b] S",
    # Mixed equi + theta: hash keys are only candidates, the full predicate filters.
    "R join[R.b=S.b and S.c!='r'] S",
    # An equality inside an `or` is not a conjunct, so it must not become a key.
    "R join[R.b=S.b or R.a=4] S",
    # Empty build side: the hash table is never populated.
    "R join[R.b=Empty.b] Empty",
    # Probes that miss every bucket (R.b=99 has no partner in S).
    "(select[a=4](R)) join[R.b=S.b] S",
    # The join is not the root, so the walker must recurse through a unary operator.
    "project[R.a, S.c](R join[R.b=S.b] S)",
    # Three-way join: every join in the plan must be switched.
    "(R join[R.b=S.b] S) join[S.c=T.c] T",
    # Self join through rename (case 20's shape): left arity is non-zero and both
    # sides come from the same base relation, which is where the keying bug lived.
    "rename[E2](Emp) join[Emp.MgrID=E2.EID] Emp",
]


@pytest.mark.parametrize("query", EQUIVALENT_QUERIES)
def test_hash_join_matches_nested_loop(query: str) -> None:
    nested_rows, hash_rows, _, _ = both_ways(query)
    assert nested_rows == hash_rows, (
        f"strategies disagree on {query!r}:\n  nested={nested_rows}\n  hash={hash_rows}"
    )


def test_hash_join_actually_switched_and_costs_less() -> None:
    """Guard against every case above passing because the plan stayed nested."""
    query = "R join[R.b=S.b] S"
    hash_plan = _switch_strategy(Binder(catalog()).bind(parse(query)), "hash")
    assert isinstance(hash_plan, BoundJoin)
    assert hash_plan.strategy == "hash"

    _, _, n_cmp, h_cmp = both_ways(query)
    assert n_cmp == 16  # |R| * |S|
    assert h_cmp < n_cmp


def test_pure_theta_join_has_no_equi_keys() -> None:
    """With no equality conjunct there is nothing to hash on, so it stays nested."""
    plan = _switch_strategy(Binder(catalog()).bind(parse("R join[R.a<S.b] S")), "hash")
    assert isinstance(plan, BoundJoin)
    assert plan.equi_keys is None
    assert plan.strategy == "nested"


def test_equi_join_defaults_to_hash_and_matches_nested() -> None:
    """Plan Q6: a detected equi-join *uses* the hash strategy by default, and
    the default plan returns exactly what the nested baseline returns."""
    query = "R join[R.b=S.b] S"
    plan = Binder(catalog()).bind(parse(query))
    assert isinstance(plan, BoundJoin)
    assert plan.strategy == "hash"
    default_rows, default_cmp = run(plan)
    nested_rows, nested_cmp = run(_switch_strategy(plan, "nested"))
    assert default_rows == nested_rows
    assert default_cmp < nested_cmp
