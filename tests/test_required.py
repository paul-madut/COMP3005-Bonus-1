"""The 25 required test cases from Section 7 of the assignment.

Cases 1-9 (lexer) and 10-17 (parser) were enabled in Phases 3 and 4;
18-25 (semantics) are enabled in Phase 5. Each test states the case number
and quotes the assignment's input.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from relalg.binder import Binder, schema_of
from relalg.catalog import Catalog
from relalg.errors import LexicalError
from relalg.errors import SchemaError as RASchemaError
from relalg.errors import SyntaxError as RASyntaxError
from relalg.errors import TypeError as RATypeError
from relalg.executor import execute
from relalg.formatter import format_table
from relalg.lexer import tokenize
from relalg.parser import parse
from relalg.tokens import TokenKind
from relalg.tree_printer import print_tree

# The Section 4.1 data, extended with what cases 19-24 need.
DB = """
Employees (EID, Name, Age, DID) = {
  E1, John, 32, D1
  E2, Alice, 28, D2
  E3, Bob, 29, D1
}
Departments (DID, DName) = {
  D1, Sales
  D2, Eng
}
Emp (EID, Name, DID, MgrID) = {
  1, 'A', 10, 1
  2, 'B', 10, 1
  3, 'C', 20, 2
}
Dept (DID, Floor) = {
  10, 1
  20, 2
}
R (a) = {
  1
  2
}
S (b) = {
  3
}
"""


def make_catalog() -> Catalog:
    c = Catalog()
    c.load(DB)
    return c


def run(c: Catalog, query: str) -> list[tuple[int | Decimal | str, ...]]:
    _, rows, _ = execute(Binder(c).bind(parse(query)))
    return list(rows)


# 7.1 Tokenizer


def test_case_01() -> None:
    """`select[x1=3](R)` parses with no whitespace anywhere."""
    kinds = [t.kind for t in tokenize("select[x1=3](R)")]
    assert kinds == [
        TokenKind.WORD,
        TokenKind.LBRACKET,
        TokenKind.WORD,
        TokenKind.COMPARISON,
        TokenKind.NUMBER,
        TokenKind.RBRACKET,
        TokenKind.LPAREN,
        TokenKind.WORD,
        TokenKind.RPAREN,
        TokenKind.EOF,
    ]


def test_case_02() -> None:
    """`select[ x1 = 3 ](R)` produces a parse tree identical to case 1."""
    t1 = print_tree(parse("select[x1=3](R)").expr)
    t2 = print_tree(parse("select[ x1 = 3 ](R)").expr)
    assert t1 == t2


def test_case_03() -> None:
    """`select[Age>=30](R)` has one >= token, not > followed by =."""
    comps = [t.text for t in tokenize("select[Age>=30](R)") if t.kind is TokenKind.COMPARISON]
    assert comps == [">="]


def test_case_04() -> None:
    """`select[Age>-30](R)` has tokens > and -30, never a >- operator."""
    toks = tokenize("select[Age>-30](R)")
    assert toks[3].text == ">" and toks[3].kind is TokenKind.COMPARISON
    assert toks[4].text == "-30" and toks[4].value == -30


def test_case_05() -> None:
    """`select[Name='Bob)'](R)`: the parenthesis is inside the string."""
    s = tokenize("select[Name='Bob)'](R)")[4]
    assert s.kind is TokenKind.STRING and s.value == "Bob)"


def test_case_06() -> None:
    """`select[Name='a,b'](R)`: the comma is inside the string."""
    s = tokenize("select[Name='a,b'](R)")[4]
    assert s.kind is TokenKind.STRING and s.value == "a,b"


def test_case_07() -> None:
    """`select[Name='O''Brien'](R)`: the doubled quote is one literal quote."""
    s = tokenize("select[Name='O''Brien'](R)")[4]
    assert s.kind is TokenKind.STRING and s.value == "O'Brien"


def test_case_08() -> None:
    """`select[union=3](R)`: an attribute may be spelled like a keyword."""
    c = make_catalog()
    c.load("T (union) = {\n 3\n}")
    assert run(c, "select[union=3](T)") == [(3,)]
    # And the lexer itself just emits a WORD.
    assert tokenize("select[union=3](R)")[2].kind is TokenKind.WORD


def test_case_09() -> None:
    """`select[Name='Bob](R)` is a lexical error with a position."""
    with pytest.raises(LexicalError) as e:
        tokenize("select[Name='Bob](R)")
    assert (e.value.line, e.value.col) == (1, 13)
    assert "1:13" in e.value.render("select[Name='Bob](R)")


# 7.2 Grammar and precedence


def test_case_10() -> None:
    """`A union B minus C` groups as documented in GRAMMAR.md."""
    expr = parse("A union B minus C").expr
    assert type(expr).__name__ == "Minus"
    assert type(expr.left).__name__ == "Union"  # type: ignore[union-attr]
    tree = print_tree(expr)
    assert tree.splitlines()[0] == "minus"
    assert "├─ union" in tree


def test_case_11() -> None:
    """`A minus B minus C` associates as documented in GRAMMAR.md."""
    expr = parse("A minus B minus C").expr
    assert type(expr).__name__ == "Minus"
    assert type(expr.left).__name__ == "Minus"  # type: ignore[union-attr]
    # And the data agrees: ({1,2,3} - {2}) - {1,2} = {3}
    c = make_catalog()
    c.load("A (x) = {\n 1\n 2\n 3\n}\nB (x) = {\n 2\n}\nC (x) = {\n 1\n 2\n}")
    assert run(c, "A minus B minus C") == [(3,)]


def test_case_12() -> None:
    """`select[not (a=1 and b=2) or c>3](R)`: not > and > or."""
    expr = parse("select[not (a=1 and b=2) or c>3](R)").expr
    assert type(expr).__name__ == "Select"
    cond = expr.cond  # type: ignore[union-attr]
    assert type(cond).__name__ == "Or"
    assert type(cond.left).__name__ == "Not"  # type: ignore[union-attr]
    assert type(cond.left.child).__name__ == "And"  # type: ignore[union-attr]


def test_case_13() -> None:
    """`select[a=1 and b=2 or c=3](R)` groups as (a=1 and b=2) or c=3."""
    expr = parse("select[a=1 and b=2 or c=3](R)").expr
    cond = expr.cond  # type: ignore[union-attr]
    assert type(cond).__name__ == "Or"
    assert type(cond.left).__name__ == "And"  # type: ignore[union-attr]


def test_case_14() -> None:
    """`project[Name](select[Age>30](select[DID='D1'](Employees)))` nests correctly."""
    expr = parse("project[Name](select[Age>30](select[DID='D1'](Employees)))").expr
    assert type(expr).__name__ == "Project"
    assert type(expr.input).__name__ == "Select"  # type: ignore[union-attr]
    assert type(expr.input.input).__name__ == "Select"  # type: ignore[union-attr]


def test_case_15() -> None:
    """`(A union B) minus (C intersect D)`: parentheses override precedence."""
    expr = parse("(A union B) minus (C intersect D)").expr
    assert type(expr).__name__ == "Minus"
    assert type(expr.left).__name__ == "Union"  # type: ignore[union-attr]
    assert type(expr.right).__name__ == "Intersect"  # type: ignore[union-attr]


def test_case_16() -> None:
    """`select[Age>30](R` is a syntax error naming the missing parenthesis."""
    with pytest.raises(RASyntaxError) as e:
        parse("select[Age>30](R")
    msg = str(e.value)
    assert "1:15" in msg and "')'" in msg and "opened at 1:15" in msg


def test_case_17() -> None:
    """`project[](R)` is a syntax error: empty attribute list."""
    with pytest.raises(RASyntaxError):
        parse("project[](R)")


# 7.3 Semantics


def test_case_18() -> None:
    """`select[A=B](R)` compares two columns, not a column to the string B."""
    c = make_catalog()
    c.load("A2 (A, B) = {\n 1, 1\n 2, 3\n}")
    assert run(c, "select[A=B](A2)") == [(1, 1)]
    # 'B' as a quoted string would be a type error on a number column.
    with pytest.raises(RATypeError):
        run(c, "select[A='B'](A2)")


def test_case_19() -> None:
    """`Emp join[Emp.DID=Dept.DID] Dept` keeps both DID columns distinguishable."""
    c = make_catalog()
    rows = run(c, "Emp join[Emp.DID=Dept.DID] Dept")
    assert len(rows) == 3
    schema = schema_of(Binder(c).bind(parse("Emp join[Emp.DID=Dept.DID] Dept")))
    names = [a.display() for a in schema.attrs]
    assert names == ["Emp.EID", "Emp.Name", "Emp.DID", "Emp.MgrID", "Dept.DID", "Dept.Floor"]
    # The unqualified name is ambiguous now.
    with pytest.raises(RASchemaError, match="ambiguous"):
        run(c, "select[DID=10](Emp join[Emp.DID=Dept.DID] Dept)")


def test_case_20() -> None:
    """`rename[E2](Emp) join[Emp.MgrID=E2.EID] Emp` is a working self join."""
    c = make_catalog()
    rows = run(c, "rename[E2](Emp) join[Emp.MgrID=E2.EID] Emp")
    # Every employee joins to their manager: 2 report to 1, 1 reports to 1.
    assert len(rows) == 3
    assert (1, "A", 10, 1, 1, "A", 10, 1) in rows


def test_case_21() -> None:
    """`R union S` with different schemas is a schema error."""
    with pytest.raises(RASchemaError):
        run(make_catalog(), "R union S")


def test_case_22() -> None:
    """`select[Age>'30'](R)` is a type error."""
    with pytest.raises(RATypeError):
        run(make_catalog(), "select[Age>'30'](Employees)")


def test_case_23() -> None:
    """`project[DID](Employees)` on the Section 4.1 data returns two tuples."""
    assert run(make_catalog(), "project[DID](Employees)") == [("D1",), ("D2",)]


def test_case_24() -> None:
    """`project[Name, Name](R)` is a schema error (duplicate output attribute)."""
    with pytest.raises(RASchemaError):
        run(make_catalog(), "project[Name, Name](Emp)")


def test_case_25() -> None:
    """A query returning no tuples prints the schema and an empty body."""
    c = make_catalog()
    out = format_table(schema_of(Binder(c).bind(parse("select[Age>999](Employees)"))), [])
    assert "(0 tuples)" in out
    assert "Employees.EID" in out and "Employees.Age" in out


def test_case_10_example_file_shows_the_grouping_difference() -> None:
    """examples/case10.ra is the data instance GRAMMAR.md section 3.3 cites.

    The demo is only convincing if the two groupings really disagree on it, so
    the file is checked rather than trusted.
    """
    from pathlib import Path

    c = Catalog()
    c.load(Path("examples/case10.ra").read_text(encoding="utf-8"))
    assert run(c, "A union B minus C") == [(2,)]
    assert run(c, "(A union B) minus C") == [(2,)]
    assert run(c, "A union (B minus C)") == [(1,), (2,)]
