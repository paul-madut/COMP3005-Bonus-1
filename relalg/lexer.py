"""Hand-written character-by-character scanner with a query mode and a tuple-body mode."""

from __future__ import annotations

from decimal import Decimal

from .errors import LexicalError, Position, Span
from .tokens import Token, TokenKind

# A bare tuple value ends at any of these characters or at whitespace.
BODY_STOPS = ",()'{}"
# Maximal munch: the longest match wins, so "<=" is one token and ">-" is two.
PAIR_TOKEN: dict[str, TokenKind] = {
    "<=": TokenKind.COMPARISON,
    ">=": TokenKind.COMPARISON,
    "!=": TokenKind.COMPARISON,
    "->": TokenKind.ARROW,
}
PUNCT_1: dict[str, TokenKind] = {
    "(": TokenKind.LPAREN,
    ")": TokenKind.RPAREN,
    "[": TokenKind.LBRACKET,
    "]": TokenKind.RBRACKET,
    "{": TokenKind.LBRACE,
    "}": TokenKind.RBRACE,
    ",": TokenKind.COMMA,
    ".": TokenKind.DOT,
    ";": TokenKind.SEMI,
}


def _is_digit(ch: str) -> bool:
    return "0" <= ch <= "9"


def _bare_value(text: str) -> int | Decimal | str:
    """A bare value is a number if it scans fully as one, otherwise it is a string."""
    sign = ""
    body = text
    if body[:1] == "-":
        sign, body = "-", body[1:]
    whole, dot, frac = body.partition(".")
    if whole.isdigit() and (not dot or frac.isdigit()):
        return int(sign + body) if not dot else Decimal(sign + body)
    return text


class Lexer:
    """Scans source text into tokens; mode switches to tuple bodies inside '{ }'."""

    def __init__(self, source: str) -> None:
        self._src = source
        self._pos = 0
        self._line = 1
        self._col = 1
        self._line_start = True  # nothing but horizontal whitespace on this line yet
        self._brace_depth = 0  # > 0 means we are inside a tuple body

    # -- low-level helpers ---------------------------------------------------

    def _peek(self, ahead: int = 0) -> str:
        i = self._pos + ahead
        return self._src[i] if i < len(self._src) else ""

    def _advance(self) -> str:
        ch = self._peek()
        if ch == "":
            return ""
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._col = 1
            self._line_start = True
        else:
            if ch not in (" ", "\t", "\r"):
                self._line_start = False
            self._col += 1
        return ch

    def _at(self, line: int, col: int, offset: int) -> Position:
        return Position(line, col, offset)

    def _error(
        self, message: str, line: int, col: int, offset: int, text: str = ""
    ) -> LexicalError:
        length = max(len(text), 1)
        span = Span(
            self._at(line, col, offset),
            self._at(line, col + length, offset + length),
        )
        return LexicalError(message, span)

    # -- token construction ----------------------------------------------------

    def _emit(
        self,
        kind: TokenKind,
        text: str,
        value: int | Decimal | str | None,
        line: int,
        col: int,
        offset: int,
    ) -> Token:
        return Token(kind, text, value, line, col, offset)

    def _scan_number(self) -> tuple[str, int | Decimal]:
        line, col, offset = self._line, self._col, self._pos
        start = self._pos
        if self._peek() == "-":
            self._advance()
        while _is_digit(self._peek()):
            self._advance()
        is_int = True
        if self._peek() == "." and _is_digit(self._peek(1)):
            is_int = False
            self._advance()  # the dot
            while _is_digit(self._peek()):
                self._advance()
        text = self._src[start : self._pos]
        nxt = self._peek()
        if nxt.isalpha() or nxt == "_":
            raise self._error(
                f"malformed number {text!r} followed by a letter (use a space)",
                line,
                col,
                offset,
                text + nxt,
            )
        return text, (int(text) if is_int else Decimal(text))

    def _scan_string(self) -> Token:
        line, col, offset = self._line, self._col, self._pos
        self._advance()  # opening quote
        pieces: list[str] = []
        while True:
            ch = self._peek()
            if ch == "" or ch == "\n":
                raise self._error(
                    "unterminated string (a string may not span lines)",
                    line,
                    col,
                    offset,
                    "'",
                )
            if ch == "'":
                # A doubled quote is an escape only once the string has content,
                # so '' is the empty string and 'O''Brien' holds one quote.
                if self._peek(1) == "'" and pieces:
                    pieces.append("'")
                    self._advance()
                    self._advance()
                    continue
                self._advance()  # closing quote
                break
            pieces.append(self._advance())
        text = self._src[offset : self._pos]
        return self._emit(TokenKind.STRING, text, "".join(pieces), line, col, offset)

    def _scan_word(self) -> Token:
        line, col, offset = self._line, self._col, self._pos
        start = self._pos
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        text = self._src[start : self._pos]
        return self._emit(TokenKind.WORD, text, text, line, col, offset)

    def _scan_bare_value(self) -> Token:
        line, col, offset = self._line, self._col, self._pos
        start = self._pos
        while True:
            ch = self._peek()
            if ch == "" or ch in BODY_STOPS or ch.isspace():
                break
            self._advance()
        text = self._src[start : self._pos]
        return self._emit(TokenKind.STRING, text, _bare_value(text), line, col, offset)

    # -- the scanner loop ------------------------------------------------------

    def next_token(self) -> Token:
        """Return the next token, scanning bare values while inside '{ ... }'."""
        while True:
            ch = self._peek()
            if ch in (" ", "\t", "\r"):
                self._advance()
                continue
            # A comment is // only at the start of a line, so a//b is never broken.
            if ch == "/" and self._peek(1) == "/" and self._line_start:
                while self._peek() not in ("", "\n"):
                    self._advance()
                continue
            if ch == "\n":
                line, col, offset = self._line, self._col, self._pos
                self._advance()
                if self._brace_depth > 0:
                    # Newlines end rows inside a tuple body, so they survive there.
                    return self._emit(TokenKind.NEWLINE, "\\n", None, line, col, offset)
                continue  # outside a tuple body a newline is plain whitespace
            break

        line, col, offset = self._line, self._col, self._pos

        if ch == "":
            return self._emit(TokenKind.EOF, "", None, line, col, offset)

        # Tuple-body mode: anything that is not body punctuation is a bare value.
        if self._brace_depth > 0 and ch not in BODY_STOPS:
            return self._scan_bare_value()

        # Maximal munch for two-character operators.
        pair = ch + self._peek(1)
        if pair in PAIR_TOKEN:
            self._advance()
            self._advance()
            return self._emit(PAIR_TOKEN[pair], pair, pair, line, col, offset)

        if ch in "<>=":
            self._advance()
            return self._emit(TokenKind.COMPARISON, ch, ch, line, col, offset)

        if ch in PUNCT_1:
            self._advance()
            if ch == "{":
                self._brace_depth += 1
            elif ch == "}" and self._brace_depth > 0:
                self._brace_depth -= 1
            return self._emit(PUNCT_1[ch], ch, None, line, col, offset)

        if ch == "'":
            return self._scan_string()

        if _is_digit(ch) or (ch == "-" and _is_digit(self._peek(1))):
            text, value = self._scan_number()
            return self._emit(TokenKind.NUMBER, text, value, line, col, offset)

        if ch.isalpha() or ch == "_":
            return self._scan_word()

        raise self._error(f"unexpected character {ch!r}", line, col, offset, ch)

    def tokenize(self) -> list[Token]:
        """Scan the whole input; the final token is always EOF."""
        out: list[Token] = []
        while True:
            tok = self.next_token()
            out.append(tok)
            if tok.kind is TokenKind.EOF:
                return out


def tokenize(source: str) -> list[Token]:
    """Convenience wrapper: scan source text into a token list."""
    return Lexer(source).tokenize()
