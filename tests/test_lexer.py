"""Unit tests for relalg.lexer (required cases 1-9 plus extra edge cases)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from relalg.errors import LexicalError
from relalg.lexer import tokenize
from relalg.tokens import TokenKind


def kinds(source: str) -> list[TokenKind]:
    return [t.kind for t in tokenize(source)]


def texts(source: str) -> list[str]:
    return [t.text for t in tokenize(source)]


# -- required cases -----------------------------------------------------------


def test_case_01() -> None:
    """select[x1=3](R) parses with no whitespace anywhere."""
    expected = [
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
    assert kinds("select[x1=3](R)") == expected
    assert texts("select[x1=3](R)") == [
        "select",
        "[",
        "x1",
        "=",
        "3",
        "]",
        "(",
        "R",
        ")",
        "",
    ]


def test_case_02() -> None:
    """Whitespace changes nothing (same token stream as case 1)."""
    assert kinds("select[ x1 = 3 ](R)") == kinds("select[x1=3](R)")
    assert texts("select[ x1 = 3 ](R)") == texts("select[x1=3](R)")


def test_case_03() -> None:
    """>= is one token, not > followed by =."""
    comps = [t.text for t in tokenize("select[Age>=30](R)") if t.kind is TokenKind.COMPARISON]
    assert comps == [">="]


def test_case_04() -> None:
    """>-30 lexes as > and -30, never a >- operator."""
    toks = tokenize("select[Age>-30](R)")
    assert [t.kind for t in toks[3:6]] == [
        TokenKind.COMPARISON,
        TokenKind.NUMBER,
        TokenKind.RBRACKET,
    ]
    assert toks[4].text == "-30"
    assert toks[4].value == -30


def test_case_05() -> None:
    """The parenthesis is inside the string."""
    s = tokenize("select[Name='Bob)'](R)")[4]
    assert s.kind is TokenKind.STRING
    assert s.value == "Bob)"


def test_case_06() -> None:
    """The comma is inside the string."""
    s = tokenize("select[Name='a,b'](R)")[4]
    assert s.kind is TokenKind.STRING
    assert s.value == "a,b"


def test_case_07() -> None:
    """The doubled quote is one literal quote."""
    s = tokenize("select[Name='O''Brien'](R)")[4]
    assert s.kind is TokenKind.STRING
    assert s.value == "O'Brien"


def test_case_08() -> None:
    """union is just a WORD to the lexer (parser decides it is an attribute)."""
    assert kinds("select[union=3](R)")[2] is TokenKind.WORD
    assert texts("select[union=3](R)")[2] == "union"


def test_case_09() -> None:
    """Unterminated string is a lexical error at the opening quote (1:13)."""
    with pytest.raises(LexicalError) as excinfo:
        tokenize("select[Name='Bob](R)")
    assert (excinfo.value.line, excinfo.value.col) == (1, 13)


# -- extra edge cases ----------------------------------------------------------


def test_float_is_exact_decimal() -> None:
    """Floats are Decimal, never float."""
    num = tokenize("select[a>1.5](R)")[4]
    assert isinstance(num.value, Decimal)
    assert num.value == Decimal("1.5")


def test_1x_is_lexical_error() -> None:
    """A number immediately followed by a letter is one lexical error."""
    with pytest.raises(LexicalError) as excinfo:
        tokenize("select[a=1x](R)")
    assert excinfo.value.line == 1


def test_gt_space_eq_is_two_tokens() -> None:
    """> = is two comparison tokens (no maximal-munch across whitespace)."""
    assert texts("select[a> =1](R)")[3:5] == [">", "="]


def test_lt_gt_is_no_operator() -> None:
    """There is no <> operator: it lexes as < then >."""
    assert kinds("select[a<>1](R)")[3:5] == [TokenKind.COMPARISON, TokenKind.COMPARISON]
    assert texts("select[a<>1](R)")[3:5] == ["<", ">"]


def test_bang_alone_is_lexical_error() -> None:
    with pytest.raises(LexicalError):
        tokenize("select[a!1](R)")
    assert texts("select[a!=1](R)")[3] == "!="


def test_arrow_token() -> None:
    assert texts("rename[a->b](R)") == [
        "rename",
        "[",
        "a",
        "->",
        "b",
        "]",
        "(",
        "R",
        ")",
        "",  # EOF
    ]


def test_comment_only_at_line_start() -> None:
    """// starts a comment only at line start, so a//b bare values survive."""
    assert kinds("  // full line comment\nR") == [TokenKind.WORD, TokenKind.EOF]
    # In query mode / is not a WORD character (GRAMMAR.md 1.2), so it is an error.
    with pytest.raises(LexicalError):
        tokenize("select[a//b=1](R)")
    # Inside a tuple body a//b is one bare string value.
    toks = tokenize("R(a) = {\n a//b\n}")
    assert [t.value for t in toks if t.kind is TokenKind.STRING] == ["a//b"]


def test_positions_are_1_based() -> None:
    toks = tokenize("select[a>1](\n  R\n)")
    r_tok = toks[7]
    assert (r_tok.line, r_tok.col, r_tok.offset) == (2, 3, 15)


def test_tuple_body_bare_values() -> None:
    """Bare values scan as STRING kind with int/Decimal/str values."""
    toks = tokenize("R (a, b) = {\n  1, x\n  2, 'two words'\n}")
    values = [t.value for t in toks if t.kind is TokenKind.STRING]
    # 'a' and 'b' are WORDs (the attribute list); the body values are 1, x, 2, 'two words'.
    assert values == [1, "x", 2, "two words"]
    # A quoted number is a string, a bare number is a number.
    toks = tokenize("R(a) = {\n 32, '32'\n}")
    assert [t.value for t in toks if t.kind is TokenKind.STRING] == [32, "32"]


def test_tuple_body_negative_number() -> None:
    toks = tokenize("R(a) = {\n-30\n}")
    values = [t.value for t in toks if t.kind is TokenKind.STRING]
    assert values == [-30]


def test_tuple_body_newlines_significant() -> None:
    """NEWLINE tokens survive inside tuple bodies (the parser needs them)."""
    toks = tokenize("R(a) = {\n1, x\n}")
    newlines = [t for t in toks if t.kind is TokenKind.NEWLINE]
    assert len(newlines) == 2


def test_unexpected_character_is_lexical_error() -> None:
    with pytest.raises(LexicalError):
        tokenize("select[a>1](R)$")
