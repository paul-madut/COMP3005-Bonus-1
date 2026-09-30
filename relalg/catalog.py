"""Loads relation definitions and queries from a file into the catalog (decision 14)."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import Position, SchemaError, Span
from .errors import SyntaxError as RASyntaxError
from .lexer import tokenize
from .nodes import Query
from .parser import Parser
from .schema import Attribute, Schema
from .tokens import Token, TokenKind
from .values import TupleKey, Type, Value, tuple_key


@dataclass(frozen=True)
class Statement:
    """One statement from a file: a definition or a query, with its text."""

    line: int
    text: str


@dataclass(frozen=True)
class Definition(Statement):
    name: str
    schema: Schema
    rows: list[tuple[Value, ...]]


@dataclass(frozen=True)
class QueryStatement(Statement):
    query: Query


def is_definition(source: str) -> bool:
    """Cheap textual check: does this statement start `Name =` or `Name (attrs) =`?

    Used by the REPL to route one statement at a time. The file loader uses the
    token-level decision in _ProgramParser._at_definition instead.
    """
    text = source.strip()
    i = 0
    while i < len(text) and (text[i].isalnum() or text[i] == "_"):
        i += 1
    if i == 0:
        return False
    rest = text[i:].lstrip()
    if rest.startswith("="):
        return True
    if rest.startswith("("):
        close = rest.find(")")
        return close != -1 and rest[close + 1 :].lstrip().startswith("=")
    return False


def _span_of(tok: Token) -> Span:
    length = max(len(tok.text), 1)
    return Span(
        Position(tok.line, tok.col, tok.offset),
        Position(tok.line, tok.col + length, tok.offset + length),
    )


def _value_type(v: Value) -> Type:
    return Type.STRING if isinstance(v, str) else Type.NUMBER


class _ProgramParser:
    """Walks the token stream of a whole file, statement by statement.

    Tokenizing the file up front (not per statement) is what makes the
    tuple-body mode work: the lexer is inside '{ ... }' exactly when it should be.
    """

    def __init__(self, source: str) -> None:
        self._source = source
        self._t = tokenize(source)
        self._i = 0

    def _peek(self, ahead: int = 0) -> Token:
        j = min(self._i + ahead, len(self._t) - 1)
        return self._t[j]

    def _next(self) -> Token:
        tok = self._t[self._i]
        if tok.kind is not TokenKind.EOF:
            self._i += 1
        return tok

    def parse(self) -> list[Statement]:
        out: list[Statement] = []
        while self._peek().kind is not TokenKind.EOF:
            if self._at_definition():
                out.append(self._definition())
            else:
                out.append(self._query())
        return out

    def _at_definition(self) -> bool:
        """`Name =` or `Name (attrs) =` starts a definition; anything else a query."""
        tok = self._peek()
        nxt = self._peek(1)
        if tok.kind is not TokenKind.WORD:
            return False
        if nxt.kind is TokenKind.LPAREN:
            # `Name (a, b) = {`: the '=' after ')' settles it (LL(3)).
            j = self._i + 2
            while j < len(self._t) and self._t[j].kind is TokenKind.WORD:
                j += 1  # attribute names
                if j < len(self._t) and self._t[j].kind is TokenKind.COMMA:
                    j += 1
            closer = self._t[j] if j < len(self._t) else self._t[-1]
            return closer.kind is TokenKind.RPAREN and self._eq_at(j + 1)
        return nxt.kind is TokenKind.COMPARISON and nxt.text == "="

    def _eq_at(self, index: int) -> bool:
        if index >= len(self._t):
            return False
        tok = self._t[index]
        return tok.kind is TokenKind.COMPARISON and tok.text == "="

    def _definition(self) -> Definition:
        name_tok = self._next()  # WORD (guaranteed by _at_definition)
        attrs: list[str] = []
        if self._peek().kind is TokenKind.LPAREN:
            self._next()
            attrs.append(self._expect_word("an attribute name"))
            while self._peek().kind is TokenKind.COMMA:
                self._next()
                attrs.append(self._expect_word("an attribute name"))
            tok = self._peek()
            if tok.kind is not TokenKind.RPAREN:
                raise RASyntaxError(
                    f"expected ')' to close the attribute list, found {tok.text!r}",
                    _span_of(tok),
                )
            self._next()
        eq = self._peek()
        if not self._eq_at(self._i):
            raise RASyntaxError("expected '=' in a relation definition", _span_of(eq))
        self._next()
        brace = self._peek()
        if brace.kind is not TokenKind.LBRACE:
            raise RASyntaxError(
                f"expected '{{' to open the relation body, found {brace.text!r}",
                _span_of(brace),
            )
        self._next()

        rows, col_types = self._rows()
        if not attrs:
            width = len(rows[0]) if rows else 0
            attrs = [f"c{i + 1}" for i in range(width)]
        if len(attrs) != len(col_types):
            # Empty body (or no attribute list): columns are unknown-typed (decision 6).
            col_types = [Type.UNKNOWN] * len(attrs)
        if rows and len(attrs) != len(rows[0]):
            raise RASyntaxError(
                f"{len(attrs)} attributes declared but rows have {len(rows[0])} values",
                _span_of(name_tok),
            )
        if len(set(attrs)) != len(attrs):
            raise RASyntaxError("duplicate attribute name in the definition", _span_of(name_tok))
        schema = Schema(
            tuple(Attribute(name_tok.text, a, col_types[i]) for i, a in enumerate(attrs))
        )
        text = self._statement_text(name_tok)
        return Definition(name_tok.line, text, name_tok.text, schema, rows)

    def _expect_word(self, what: str) -> str:
        tok = self._peek()
        if tok.kind is not TokenKind.WORD:
            shown = repr(tok.text) if tok.text else "end of input"
            raise RASyntaxError(f"expected {what}, found {shown}", _span_of(tok))
        self._next()
        return tok.text

    def _rows(self) -> tuple[list[tuple[Value, ...]], list[Type]]:
        """Parse tuple rows until '}'.  Infers one type per column (decision 6)."""
        rows: list[tuple[Value, ...]] = []
        col_types: list[Type] = []
        while True:
            tok = self._peek()
            if tok.kind is TokenKind.RBRACE:
                self._next()
                break
            if tok.kind is TokenKind.NEWLINE:
                self._next()
                continue
            if tok.kind is TokenKind.EOF:
                raise RASyntaxError("unterminated relation body: missing '}'", _span_of(tok))
            row = self._row()
            if rows and len(row) != len(rows[0]):
                raise RASyntaxError(
                    f"row has {len(row)} values, expected {len(rows[0])}",
                    _span_of(tok),
                )
            if not col_types:
                col_types = [Type.UNKNOWN] * len(row)
            for i, v in enumerate(row):
                t = _value_type(v)
                if col_types[i] is Type.UNKNOWN:
                    col_types[i] = t
                elif col_types[i] is not t:
                    raise RASyntaxError(
                        f"mixed column types: column {i + 1} has a "
                        f"{col_types[i].value} value and now a {t.value} value",
                        _span_of(tok),
                    )
            rows.append(row)
        return rows, col_types

    def _row(self) -> tuple[Value, ...]:
        values: list[Value] = []
        while True:
            tok = self._peek()
            if tok.kind in (TokenKind.STRING, TokenKind.NUMBER):
                self._next()
                values.append(tok.value)  # type: ignore[arg-type]
            else:
                break
            if self._peek().kind is TokenKind.COMMA:
                self._next()
                continue
            break
        if not values:
            tok = self._peek()
            shown = repr(tok.text) if tok.text else "end of input"
            raise RASyntaxError(f"expected a value, found {shown}", _span_of(tok))
        return tuple(values)

    def _query(self) -> QueryStatement:
        start_tok = self._peek()
        start = self._i
        while self._peek().kind not in (TokenKind.SEMI, TokenKind.EOF):
            self._next()
        end_tok = self._peek()
        body = self._t[start : self._i]  # up to, but excluding, ';' or EOF
        if end_tok.kind is TokenKind.SEMI:
            self._next()
        if not body:
            raise RASyntaxError("empty query", _span_of(start_tok))
        # The sub-parser still needs an EOF sentinel at the end of its stream.
        query = Parser(self._source, body + [self._t[-1]]).parse_query()
        text = self._statement_text(body[0], body[-1])
        return QueryStatement(start_tok.line, text, query)

    def _statement_text(self, first: Token, last: Token | None = None) -> str:
        end = (last or first).offset + max(len((last or first).text), 1)
        return self._source[first.offset : end].strip()


class Catalog:
    """Named relations plus the queries read from a file."""

    def __init__(self) -> None:
        self._schemas: dict[str, Schema] = {}
        self._rows: dict[str, list[tuple[Value, ...]]] = {}
        self.order: list[str] = []
        self.queries: list[QueryStatement] = []

    def add(self, name: str, schema: Schema, rows: list[tuple[Value, ...]]) -> None:
        if name in self._schemas:
            raise SchemaError(f"relation {name!r} is already defined")
        self._schemas[name] = schema
        # Decision 12: relations are sets of tuples, insertion-ordered.
        seen: dict[TupleKey, tuple[Value, ...]] = {}
        for row in rows:
            seen.setdefault(tuple_key(row), row)
        self._rows[name] = list(seen.values())
        self.order.append(name)

    def schema(self, name: str) -> Schema:
        return self._schemas[name]

    def rows(self, name: str) -> list[tuple[Value, ...]]:
        return self._rows[name]

    def has(self, name: str) -> bool:
        return name in self._schemas

    def names(self) -> list[str]:
        return list(self.order)

    def load(self, source: str) -> None:
        """Parse a file into definitions and queries (decision 14)."""
        for st in _ProgramParser(source).parse():
            if isinstance(st, Definition):
                self.add(st.name, st.schema, st.rows)
            elif isinstance(st, QueryStatement):
                self.queries.append(st)

    def load_statement(self, source: str, line: int = 1) -> None:
        """Parse and apply a single REPL statement."""
        if is_definition(source):
            st = _ProgramParser(source).parse()[0]
            assert isinstance(st, Definition)
            self.add(st.name, st.schema, st.rows)
            return
        query = Parser(source).parse_query()
        self.queries.append(QueryStatement(line, source, query))
