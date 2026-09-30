"""Token kinds and the Token record (kind, text, value, line, column, offset)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto


class TokenKind(Enum):
    WORD = auto()  # relation names, attribute names and keywords alike
    NUMBER = auto()  # value is int or Decimal, never float
    STRING = auto()  # value is the decoded string; also used for bare tuple values
    COMPARISON = auto()  # =  !=  <  <=  >  >=
    ARROW = auto()  # -> in rename[old->new]
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LBRACE = auto()
    RBRACE = auto()
    COMMA = auto()
    DOT = auto()
    SEMI = auto()
    NEWLINE = auto()  # significant inside tuple bodies, whitespace-like elsewhere
    EOF = auto()


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    value: int | Decimal | str | None
    line: int
    col: int
    offset: int
