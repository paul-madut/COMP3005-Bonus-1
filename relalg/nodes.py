"""Parse tree node types for expressions and conditions, each carrying its source span."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .errors import Span

# -- expressions -----------------------------------------------------------


@dataclass(frozen=True)
class Relation:
    """A base relation referenced by name."""

    name: str
    span: Span


@dataclass(frozen=True)
class Select:
    """select[cond](input)"""

    cond: Cond
    input: Expr
    span: Span


@dataclass(frozen=True)
class Project:
    """project[a, b, ...](input)"""

    attrs: list[AttrRef]
    input: Expr
    span: Span


@dataclass(frozen=True)
class Rename:
    """rename[New](input) or rename[old->new, ...](input)"""

    rel_name: str | None
    columns: list[tuple[AttrRef, str]]  # (reference to the old name, new name)
    input: Expr
    span: Span


@dataclass(frozen=True)
class Union:
    """left union right"""

    left: Expr
    right: Expr
    span: Span


@dataclass(frozen=True)
class Minus:
    """left minus right"""

    left: Expr
    right: Expr
    span: Span


@dataclass(frozen=True)
class Intersect:
    """left intersect right"""

    left: Expr
    right: Expr
    span: Span


@dataclass(frozen=True)
class Times:
    """left times right"""

    left: Expr
    right: Expr
    span: Span


@dataclass(frozen=True)
class Join:
    """left join[cond] right"""

    cond: Cond
    left: Expr
    right: Expr
    span: Span


Expr = Relation | Select | Project | Rename | Union | Minus | Intersect | Times | Join

# -- conditions ------------------------------------------------------------


@dataclass(frozen=True)
class AttrRef:
    """An attribute reference: plain `name` or qualified `qualifier.name`."""

    qualifier: str | None
    name: str
    span: Span


@dataclass(frozen=True)
class Literal:
    """A number or string literal in a condition."""

    value: int | Decimal | str
    span: Span


@dataclass(frozen=True)
class Comparison:
    """left compop right, with op one of = != < <= > >="""

    op: str
    left: Operand
    right: Operand
    span: Span


@dataclass(frozen=True)
class Not:
    """not cond"""

    child: Cond
    span: Span


@dataclass(frozen=True)
class And:
    """left and right"""

    left: Cond
    right: Cond
    span: Span


@dataclass(frozen=True)
class Or:
    """left or right"""

    left: Cond
    right: Cond
    span: Span


Cond = Comparison | Not | And | Or

Operand = AttrRef | Literal

# -- statements ------------------------------------------------------------


@dataclass(frozen=True)
class Query:
    """One query (no trailing ';') plus its full text span."""

    expr: Expr
    span: Span
