"""Types, comparison semantics, and the single definition of tuple equality.

Decision 12: every equality question goes through `values_equal` / `tuple_key`
so set semantics are consistent everywhere.  Numbers are int or Decimal, never
float (decision 4).
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from .errors import Span
from .errors import TypeError as RATypeError

Value = int | Decimal | str
# The hashable key form of a tuple, as produced by tuple_key().
TupleKey = tuple[str | int | Decimal | tuple[str, str], ...]


class Type(Enum):
    """The two data types plus `unknown` for empty columns (decision 6)."""

    NUMBER = "number"
    STRING = "string"
    UNKNOWN = "unknown"


UNKNOWN = Type.UNKNOWN
NUMBER = Type.NUMBER
STRING = Type.STRING


def type_of(value: Value) -> Type:
    if isinstance(value, str):
        return STRING
    return NUMBER


def compatible(left: Type, right: Type) -> bool:
    """Two types are compatible unless both are known and different.

    `unknown` (an empty column) is compatible with anything (decision 6).
    """
    if left is UNKNOWN or right is UNKNOWN:
        return True
    return left is right


def compare(
    op: str, left: Value, right: Value, span: Span | None, ltype: Type, rtype: Type
) -> bool:
    """Apply a comparison operator; cross-type comparisons are a type error.

    Equality uses `values_equal`; ordering requires numbers on both sides.
    The engine compares strings lexicographically and numbers exactly.
    """
    if not compatible(ltype, rtype):
        raise RATypeError(f"cannot compare {ltype.value} with {rtype.value}", span)
    if op == "=":
        return values_equal(left, right)
    if op == "!=":
        return not values_equal(left, right)
    # Ordering: meaningful only between two numbers (or two strings).
    if isinstance(left, str) != isinstance(right, str):
        raise RATypeError(
            f"ordering {op!r} requires two numbers or two strings, "
            f"got {ltype.value} and {rtype.value}",
            span,
        )
    a: Decimal | int | str
    b: Decimal | int | str
    a, b = left, right
    if op == "<":
        return a < b  # type: ignore[operator]  # narrowed same-kind above
    if op == "<=":
        return a <= b  # type: ignore[operator]
    if op == ">":
        return a > b  # type: ignore[operator]
    if op == ">=":
        return a >= b  # type: ignore[operator]
    raise AssertionError(f"unknown comparison operator {op!r}")


def values_equal(left: Value, right: Value) -> bool:
    """The one definition of value equality (decision 12).

    int and Decimal compare by numeric value (1 == 1.0); strings by content.
    A number never equals a string, even when it looks like one ('32' != 32).
    """
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    return left == right


def tuple_key(t: tuple[Value, ...]) -> TupleKey:
    """A hashable key for a whole tuple, used for dedup and set operations."""
    return tuple((type(v).__name__, v) if isinstance(v, str) else v for v in t)


def format_value(v: Value) -> str:
    """Render a value in this language's own syntax, never Python's.

    Strings are single-quoted with `''` for an embedded quote, so output can be
    pasted back into a relation file.  Numbers print as written: `repr` would
    turn a Decimal into `Decimal('1.5')` and leak the implementation into error
    messages and result tables.
    """
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    return str(v)
