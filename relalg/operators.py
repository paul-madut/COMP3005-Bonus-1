"""The eight relational operators as Volcano-style generators + stats (decision 13).

Each operator is a generator function whose parent pulls tuples with `next()`.
Each operator owns a Stats object (rows in, rows out, comparisons, time) so
`--stats` can print an EXPLAIN ANALYZE-style tree.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field

from .binder import (
    BoundIntersect,
    BoundJoin,
    BoundMinus,
    BoundNode,
    BoundProject,
    BoundRelation,
    BoundRename,
    BoundSelect,
    BoundTimes,
    BoundUnion,
    schema_of,
)
from .schema import Schema
from .values import TupleKey, Value, tuple_key


@dataclass
class Stats:
    """Per-operator counters, in the spirit of EXPLAIN ANALYZE (decision 13)."""

    label: str
    rows_out: int = 0
    rows_in: int = 0
    comparisons: int = 0
    time_ns: int = 0
    children: list[Stats] = field(default_factory=list)

    def total_ns(self) -> int:
        return self.time_ns + sum(c.total_ns() for c in self.children)


Row = tuple[Value, ...]


class _Operator:
    """Base class: wraps a generator, counts rows out and elapsed time."""

    def __init__(self, label: str, stats: Stats) -> None:
        self._label = label
        self.stats = stats

    def _pull(self, gen: Iterator[Row]) -> Iterator[Row]:
        while True:
            t0 = time.perf_counter_ns()
            try:
                row = next(gen)
            except StopIteration:
                self.stats.time_ns += time.perf_counter_ns() - t0
                return
            self.stats.time_ns += time.perf_counter_ns() - t0
            self.stats.rows_out += 1
            yield row


def _open(node: BoundNode, stats: Stats) -> Iterator[Row]:
    """Return the tuple generator for a bound node, wiring stats children."""
    match node:
        case BoundRelation():
            stats.children.append(Stats(f"scan {node.name}"))
            child = stats.children[-1]
            return _pull_relation(node, child)
        case BoundSelect():
            child = Stats("select")
            stats.children.append(child)
            return _pull_select(node, child, _open(node.input, child))
        case BoundProject():
            child = Stats("project")
            stats.children.append(child)
            return _pull_project(node, child, _open(node.input, child))
        case BoundRename():
            return _open(node.input, stats)  # schema-only operator
        case BoundUnion():
            child = Stats("union")
            stats.children.append(child)
            return _pull_union(node, child, _open(node.left, child), _open(node.right, child))
        case BoundMinus():
            child = Stats("minus")
            stats.children.append(child)
            return _pull_minus(node, child, _open(node.left, child), _open(node.right, child))
        case BoundIntersect():
            child = Stats("intersect")
            stats.children.append(child)
            return _pull_intersect(node, child, _open(node.left, child), _open(node.right, child))
        case BoundTimes():
            child = Stats("times")
            stats.children.append(child)
            return _pull_times(node, child, _open(node.left, child), _open(node.right, child))
        case BoundJoin():
            child = Stats("join")
            stats.children.append(child)
            return _pull_join(node, child, _open(node.left, child), _open(node.right, child))
    raise AssertionError(f"unreachable bound node {node!r}")


def _pull_relation(node: BoundRelation, stats: Stats) -> Iterator[Row]:
    for row in node.rows:
        stats.rows_out += 1
        yield row


def _pull_select(node: BoundSelect, stats: Stats, inner: Iterator[Row]) -> Iterator[Row]:
    pred = node.cond
    for row in inner:
        stats.rows_in += 1
        stats.comparisons += 1
        if pred(row):
            stats.rows_out += 1
            yield row


def _pull_project(node: BoundProject, stats: Stats, inner: Iterator[Row]) -> Iterator[Row]:
    idx = node.indexes
    seen: set[TupleKey] = set()
    for row in inner:
        stats.rows_in += 1
        # Projection is set semantics: duplicates of the projected tuple collapse.
        key = tuple_key(tuple(row[i] for i in idx))
        if key not in seen:
            seen.add(key)
            stats.rows_out += 1
            yield tuple(row[i] for i in idx)


def _pull_union(
    node: BoundUnion, stats: Stats, left: Iterator[Row], right: Iterator[Row]
) -> Iterator[Row]:
    seen: set[TupleKey] = set()
    for src in (left, right):
        for row in src:
            stats.rows_in += 1
            key = tuple_key(row)
            if key not in seen:
                seen.add(key)
                stats.rows_out += 1
                yield row


def _pull_minus(
    node: BoundMinus, stats: Stats, left: Iterator[Row], right: Iterator[Row]
) -> Iterator[Row]:
    # Materialize the right side, then probe for each left tuple.
    sub: set[TupleKey] = set()
    for row in right:
        stats.rows_in += 1
        sub.add(tuple_key(row))
    for row in left:
        stats.rows_in += 1
        if tuple_key(row) not in sub:
            stats.rows_out += 1
            yield row


def _pull_intersect(
    node: BoundIntersect, stats: Stats, left: Iterator[Row], right: Iterator[Row]
) -> Iterator[Row]:
    sub: set[TupleKey] = set()
    for row in right:
        stats.rows_in += 1
        sub.add(tuple_key(row))
    seen: set[TupleKey] = set()
    for row in left:
        stats.rows_in += 1
        key = tuple_key(row)
        if key in sub and key not in seen:
            seen.add(key)
            stats.rows_out += 1
            yield row


def _pull_times(
    node: BoundTimes, stats: Stats, left: Iterator[Row], right: Iterator[Row]
) -> Iterator[Row]:
    # Materialize the right side; every left tuple pairs with every right tuple.
    right_rows: list[Row] = list(right)
    stats.rows_in += len(right_rows)
    for lrow in left:
        stats.rows_in += 1
        for rrow in right_rows:
            stats.rows_out += 1
            yield lrow + rrow


def _pull_join(
    node: BoundJoin, stats: Stats, left: Iterator[Row], right: Iterator[Row]
) -> Iterator[Row]:
    if node.strategy == "hash" and node.equi_keys:
        yield from _pull_hash_join(node, stats, left, right)
        return
    # Decision 11: fused nested loop.  The condition is evaluated on
    # (left_row, right_row); the cross product is never materialized.
    right_rows: list[Row] = list(right)
    stats.rows_in += len(right_rows)
    pred = node.cond
    for lrow in left:
        stats.rows_in += 1
        for rrow in right_rows:
            stats.comparisons += 1
            if pred(lrow + rrow):
                stats.rows_out += 1
                yield lrow + rrow


def _pull_hash_join(
    node: BoundJoin, stats: Stats, left: Iterator[Row], right: Iterator[Row]
) -> Iterator[Row]:
    """Equi-join strategy (Q6): build a hash table on S's keys, probe with R.

    O(n+m) hash operations instead of n*m comparisons.  The emission order is
    the same as the nested loop's (left rows in order, matches in right
    insertion order), so the strategy is invisible in the output; --stats
    labels it anyway.
    """
    keys = node.equi_keys or ()
    l_arity = len(schema_of(node.left).attrs)
    l_idx = tuple(i for i, _ in keys)
    r_idx = tuple(j - l_arity for _, j in keys)  # right-side coordinates
    table: dict[TupleKey, list[Row]] = {}
    for rrow in right:
        stats.rows_in += 1
        k = tuple(rrow[j] for j in r_idx)
        table.setdefault(k, []).append(rrow)
    stats.label = "join (hash)"
    pred = node.cond
    for lrow in left:
        stats.rows_in += 1
        stats.comparisons += 1  # one probe per left tuple
        bucket = table.get(tuple(lrow[i] for i in l_idx), [])
        for rrow in bucket:
            stats.comparisons += 1
            if pred(lrow + rrow):
                stats.rows_out += 1
                yield lrow + rrow


def execute(node: BoundNode) -> tuple[Schema, Iterator[Row], Stats]:
    """Open a bound plan: returns the schema, the tuple stream and the stats tree.

    The root `plan` stats node counts what the caller actually pulls, so a fully
    consumed stream shows the plan's true row total.
    """
    root = Stats("plan")
    rows = _open(node, root)

    def _counted() -> Iterator[Row]:
        while True:
            t0 = time.perf_counter_ns()
            try:
                row = next(rows)
            except StopIteration:
                root.time_ns += time.perf_counter_ns() - t0
                return
            root.time_ns += time.perf_counter_ns() - t0
            root.rows_out += 1
            yield row

    return schema_of(node), _counted(), root
