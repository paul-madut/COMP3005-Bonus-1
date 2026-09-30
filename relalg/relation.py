"""A relation is a schema plus an insertion-ordered set of tuples (decision 12)."""

from __future__ import annotations

from collections.abc import Iterator

from .schema import Schema
from .values import TupleKey, Value, tuple_key

Row = tuple[Value, ...]


class Relation:
    """Schema + ordered set semantics via a dict keyed on tuple_key."""

    def __init__(self, schema: Schema, rows: list[Row] | None = None) -> None:
        self.schema = schema
        self._rows: dict[TupleKey, Row] = {}
        for row in rows or []:
            self.add(row)

    def add(self, row: tuple[Value, ...]) -> None:
        """Add a tuple; duplicates are ignored (set semantics)."""
        if len(row) != len(self.schema):
            raise AssertionError(
                f"arity mismatch: tuple has {len(row)} fields, schema has {len(self.schema)}"
            )
        self._rows.setdefault(tuple_key(row), row)

    def tuples(self) -> list[Row]:
        """The tuples in insertion order - deterministic output order."""
        return list(self._rows.values())

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[Row]:
        return iter(self._rows.values())
