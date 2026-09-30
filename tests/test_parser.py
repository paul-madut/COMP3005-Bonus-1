"""Unit tests for relalg.parser (required cases 10-17 plus extra edge cases)."""

from __future__ import annotations

import pytest

from relalg import nodes
from relalg.errors import SyntaxError as RASyntaxError
from relalg.parser import parse
from relalg.tree_printer import print_tree


def rel(x: nodes.Expr) -> nodes.Relation:
    """Narrow an Expr to a Relation so mypy can follow attribute access."""
    assert isinstance(x, nodes.Relation)
    return x


def test_case_10() -> None:
    """A union B minus C groups as (A union B) minus C."""
    q = parse("A union B minus C")
    expr = q.expr
    assert isinstance(expr, nodes.Minus)
    union = expr.left
    assert isinstance(union, nodes.Union)
    assert rel(union.left).name == "A"
    assert rel(union.right).name == "B"
    assert rel(expr.right).name == "C"


def test_case_11() -> None:
    """A minus B minus C associates to the left."""
    q = parse("A minus B minus C")
    expr = q.expr
    assert isinstance(expr, nodes.Minus)
    assert rel(expr.right).name == "C"
    left = expr.left
    assert isinstance(left, nodes.Minus)


def test_case_12() -> None:
    """not binds tighter than and, which binds tighter than or."""
    q = parse("select[not (a=1 and b=2) or c>3](R)")
    expr = q.expr
    assert isinstance(expr, nodes.Select)
    cond = expr.cond
    assert isinstance(cond, nodes.Or)
    assert isinstance(cond.left, nodes.Not)
    assert isinstance(cond.left.child, nodes.And)
    assert isinstance(cond.right, nodes.Comparison)


def test_case_13() -> None:
    """a=1 and b=2 or c=3 groups as (a=1 and b=2) or c=3."""
    q = parse("select[a=1 and b=2 or c=3](R)")
    expr = q.expr
    assert isinstance(expr, nodes.Select)
    cond = expr.cond
    assert isinstance(cond, nodes.Or)
    assert isinstance(cond.left, nodes.And)


def test_case_14() -> None:
    """Unary operators nest correctly."""
    q = parse("project[Name](select[Age>30](select[DID='D1'](Employees)))")
    expr = q.expr
    assert isinstance(expr, nodes.Project)
    assert isinstance(expr.input, nodes.Select)
    assert isinstance(expr.input.input, nodes.Select)


def test_case_15() -> None:
    """Parentheses override precedence."""
    q = parse("(A union B) minus (C intersect D)")
    expr = q.expr
    assert isinstance(expr, nodes.Minus)
    assert isinstance(expr.left, nodes.Union)
    assert isinstance(expr.right, nodes.Intersect)


def test_case_16() -> None:
    """Missing closing parenthesis is a syntax error naming the open one."""
    with pytest.raises(RASyntaxError) as excinfo:
        parse("select[Age>30](R")
    msg = str(excinfo.value)
    assert "')'" in msg and "1:15" in msg


def test_case_17() -> None:
    """project[] is a syntax error: empty attribute list."""
    with pytest.raises(RASyntaxError):
        parse("project[](R)")


# -- extra grammar behavior ------------------------------------------------------


def test_intersect_binds_tighter_than_union() -> None:
    q = parse("A union B intersect C")
    expr = q.expr
    assert isinstance(expr, nodes.Union)
    assert isinstance(expr.right, nodes.Intersect)


def test_times_and_join_left_associative() -> None:
    q = parse("A times B times C")
    expr = q.expr
    assert isinstance(expr, nodes.Times)
    assert isinstance(expr.left, nodes.Times)

    q = parse("A join[A.x=B.x] B join[A.y=C.y] C")
    expr = q.expr
    assert isinstance(expr, nodes.Join)
    assert isinstance(expr.left, nodes.Join)


def test_select_binds_tighter_than_times() -> None:
    q = parse("select[a>1](R) times S")
    expr = q.expr
    assert isinstance(expr, nodes.Times)
    assert isinstance(expr.left, nodes.Select)


def test_keywords_are_contextual() -> None:
    """ "union" can be an attribute or a relation (case 8 at parser level)."""
    q = parse("select[union=3](R)")
    expr = q.expr
    assert isinstance(expr, nodes.Select)
    cond = expr.cond
    assert isinstance(cond, nodes.Comparison)
    left = cond.left
    assert isinstance(left, nodes.AttrRef)
    assert left.name == "union"

    q = parse("union")  # a relation literally named "union"
    assert isinstance(q.expr, nodes.Relation)
    assert q.expr.name == "union"


def test_rename_relation_and_columns() -> None:
    q = parse("rename[E2](Emp)")
    expr = q.expr
    assert isinstance(expr, nodes.Rename)
    assert expr.rel_name == "E2"
    assert expr.columns == []

    q = parse("rename[a->x, E.b->y](E)")
    expr = q.expr
    assert isinstance(expr, nodes.Rename)
    assert expr.rel_name is None
    assert [(old.name, new) for old, new in expr.columns] == [("a", "x"), ("b", "y")]
    assert expr.columns[1][0].qualifier == "E"


def test_qualified_attr_in_condition() -> None:
    q = parse("select[R.a >= 10 and not S.c='x'](R join[R.b=S.b] S)")
    expr = q.expr
    assert isinstance(expr, nodes.Select)
    cond = expr.cond
    assert isinstance(cond, nodes.And)
    left = cond.left
    assert isinstance(left, nodes.Comparison)
    lref = left.left
    assert isinstance(lref, nodes.AttrRef)
    assert (lref.qualifier, lref.name) == ("R", "a")


def test_semi_is_optional_in_queries() -> None:
    assert parse("A union B;").expr == parse("A union B").expr


def test_trailing_garbage_rejected() -> None:
    with pytest.raises(RASyntaxError):
        parse("A B")
    with pytest.raises(RASyntaxError):
        parse("A )")


def test_join_condition_may_be_full_cond() -> None:
    q = parse("R join[not (a=1) or b>2] S")
    expr = q.expr
    assert isinstance(expr, nodes.Join)
    assert isinstance(expr.cond, nodes.Or)


# -- tree printer -----------------------------------------------------------------


def test_tree_shape_for_case_10() -> None:
    tree = print_tree(parse("A union B minus C").expr)
    assert tree == "\n".join(
        [
            "minus",
            "├─ union",
            "│  ├─ A",
            "│  └─ B",
            "└─ C",
        ]
    )


def test_tree_condition_subtrees() -> None:
    tree = print_tree(parse("select[a=1 and b=2](R)").expr)
    assert tree == "\n".join(
        [
            "select",
            "├─ and",
            "│  ├─ a = 1",
            "│  └─ b = 2",
            "└─ R",
        ]
    )


def test_tree_byte_identical_for_whitespace() -> None:
    """Case 2 at the tree level: whitespace must not change the printed tree."""
    t1 = print_tree(parse("select[x1=3](R)").expr)
    t2 = print_tree(parse("select[ x1 = 3 ](R)").expr)
    assert t1 == t2


def test_deep_parens_error_not_crash() -> None:
    """5000 nested parens give a clean syntax error, not RecursionError."""
    query = "select[a=1](" * 2500 + "R" + ")" * 2500
    with pytest.raises(RASyntaxError) as excinfo:
        parse(query)
    assert "nested too deeply" in str(excinfo.value)
