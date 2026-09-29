"""The 25 required test cases from Section 7 of the assignment.

Each test is skipped until the phase that implements it (see PLAN.md).
Remove the marker and write the assertions when that phase starts.
"""

import pytest

LEXER = pytest.mark.skip(reason="pending Phase 3: lexer")
PARSER = pytest.mark.skip(reason="pending Phase 4: parser")
SEMANTICS = pytest.mark.skip(reason="pending Phase 5: semantics")


# 7.1 Tokenizer


@LEXER
def test_case_01() -> None:
    """`select[x1=3](R)` parses with no whitespace anywhere."""


@LEXER
def test_case_02() -> None:
    """`select[ x1 = 3 ](R)` produces a parse tree identical to case 1."""


@LEXER
def test_case_03() -> None:
    """`select[Age>=30](R)` has one >= token, not > followed by =."""


@LEXER
def test_case_04() -> None:
    """`select[Age>-30](R)` has tokens > and -30, never a >- operator."""


@LEXER
def test_case_05() -> None:
    """`select[Name='Bob)'](R)`: the parenthesis is inside the string."""


@LEXER
def test_case_06() -> None:
    """`select[Name='a,b'](R)`: the comma is inside the string."""


@LEXER
def test_case_07() -> None:
    """`select[Name='O''Brien'](R)`: the doubled quote is one literal quote."""


@LEXER
def test_case_08() -> None:
    """`select[union=3](R)`: an attribute may be spelled like a keyword."""


@LEXER
def test_case_09() -> None:
    """`select[Name='Bob](R)` is a lexical error with a position."""


# 7.2 Grammar and precedence


@PARSER
def test_case_10() -> None:
    """`A union B minus C` groups as documented in GRAMMAR.md."""


@PARSER
def test_case_11() -> None:
    """`A minus B minus C` associates as documented in GRAMMAR.md."""


@PARSER
def test_case_12() -> None:
    """`select[not (a=1 and b=2) or c>3](R)`: not > and > or."""


@PARSER
def test_case_13() -> None:
    """`select[a=1 and b=2 or c=3](R)` groups as (a=1 and b=2) or c=3."""


@PARSER
def test_case_14() -> None:
    """`project[Name](select[Age>30](select[DID='D1'](Employees)))` nests correctly."""


@PARSER
def test_case_15() -> None:
    """`(A union B) minus (C intersect D)`: parentheses override precedence."""


@PARSER
def test_case_16() -> None:
    """`select[Age>30](R` is a syntax error naming the missing parenthesis."""


@PARSER
def test_case_17() -> None:
    """`project[](R)` is a syntax error: empty attribute list."""


# 7.3 Semantics


@SEMANTICS
def test_case_18() -> None:
    """`select[A=B](R)` compares two columns, not a column to the string B."""


@SEMANTICS
def test_case_19() -> None:
    """`Emp join[Emp.DID=Dept.DID] Dept` keeps both DID columns distinguishable."""


@SEMANTICS
def test_case_20() -> None:
    """`rename[E2](Emp) join[Emp.MgrID=E2.EID] Emp` is a working self join."""


@SEMANTICS
def test_case_21() -> None:
    """`R union S` with different schemas is a schema error."""


@SEMANTICS
def test_case_22() -> None:
    """`select[Age>'30'](R)` is a type error."""


@SEMANTICS
def test_case_23() -> None:
    """`project[DID](Employees)` on the Section 4.1 data returns two tuples."""


@SEMANTICS
def test_case_24() -> None:
    """`project[Name, Name](R)` is a schema error (duplicate output attribute)."""


@SEMANTICS
def test_case_25() -> None:
    """A query returning no tuples prints the schema and an empty body."""
