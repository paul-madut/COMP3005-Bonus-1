"""Recursive descent parser: one method per grammar rule in GRAMMAR.md."""

from __future__ import annotations

from decimal import Decimal

from . import nodes
from .errors import Position, Span
from .errors import SyntaxError as RASyntaxError
from .lexer import tokenize as _tokenize
from .tokens import Token, TokenKind

UNARY_OPS = ("select", "project", "rename")
SET_OPS = ("union", "minus", "intersect")
JOIN_WORD = "join"
TIMES_WORD = "times"
COMP_OPS = ("=", "!=", "<", "<=", ">", ">=")
MAX_DEPTH = 200  # clean "nested too deeply" error instead of RecursionError


class Parser:
    def __init__(
        self, source: str, tokens: list[Token] | None = None, depth_limit: int = MAX_DEPTH
    ) -> None:
        self._source = source
        self._tokens = tokens if tokens is not None else _tokenize(source)
        self._i = 0
        self._depth = 0
        self._depth_limit = depth_limit

    # -- helpers -------------------------------------------------------------

    def _peek(self, ahead: int = 0) -> Token:
        j = min(self._i + ahead, len(self._tokens) - 1)
        return self._tokens[j]

    def _next(self) -> Token:
        tok = self._tokens[self._i]
        if tok.kind is not TokenKind.EOF:
            self._i += 1
        return tok

    def _pos(self, tok: Token) -> Position:
        return Position(tok.line, tok.col, tok.offset)

    def _tok_span(self, tok: Token) -> Span:
        start = self._pos(tok)
        end = Position(tok.line, tok.col + len(tok.text), tok.offset + len(tok.text))
        return Span(start, end)

    def _at_end(self) -> bool:
        return self._peek().kind is TokenKind.EOF

    def _word_is(self, tok: Token, word: str) -> bool:
        return tok.kind is TokenKind.WORD and tok.text == word

    def _fail(self, message: str, tok: Token) -> RASyntaxError:
        return RASyntaxError(message, self._tok_span(tok))

    def _expect(self, kind: TokenKind, what: str) -> Token:
        tok = self._peek()
        if tok.kind is not kind:
            raise self._fail(f"expected {what}, found {self._describe(tok)}", tok)
        return self._next()

    def _expect_close(self, kind: TokenKind, what: str, open_tok: Token) -> Token:
        """Expect a closing delimiter and name where it was opened on failure."""
        tok = self._peek()
        if tok.kind is not kind:
            op = self._describe(open_tok)
            where = f" opened at {open_tok.line}:{open_tok.col}"
            raise self._fail(
                f"expected {what} to close {op}{where}, found {self._describe(tok)}", tok
            )
        return self._next()

    def _describe(self, tok: Token) -> str:
        if tok.kind is TokenKind.EOF:
            return "end of input"
        return f"{tok.text!r}"

    def _expect_word(self, word: str) -> Token:
        tok = self._peek()
        if not self._word_is(tok, word):
            raise self._fail(f"expected {word!r}, found {self._describe(tok)}", tok)
        return self._next()

    def _enter(self) -> None:
        self._depth += 1
        if self._depth > self._depth_limit:
            tok = self._peek()
            raise self._fail("expression nested too deeply", tok)

    def _leave(self) -> None:
        self._depth -= 1

    # -- entry points ----------------------------------------------------------

    def parse_query(self) -> nodes.Query:
        expr = self.parse_expr()
        if self._peek().kind is TokenKind.SEMI:
            self._next()
        tok = self._peek()
        if tok.kind is not TokenKind.EOF:
            raise self._fail(f"unexpected {self._describe(tok)} after the query", tok)
        return nodes.Query(expr=expr, span=expr.span)

    # -- expressions: expr > setterm > product > primary  (GRAMMAR.md 1.4) --

    def parse_expr(self) -> nodes.Expr:
        self._enter()
        try:
            left = self.parse_setterm()
            while self._peek().kind is TokenKind.WORD and self._peek().text in (
                "union",
                "minus",
            ):
                op_tok = self._next()
                right = self.parse_setterm()
                left = self._make_set_op(op_tok, left, right)
            return left
        finally:
            self._leave()

    def _make_set_op(self, op_tok: Token, left: nodes.Expr, right: nodes.Expr) -> nodes.Expr:
        span = Span(self._span_start(left), self._span_end(right))
        if op_tok.text == "union":
            return nodes.Union(left=left, right=right, span=span)
        return nodes.Minus(left=left, right=right, span=span)

    def parse_setterm(self) -> nodes.Expr:
        self._enter()
        try:
            left = self.parse_product()
            while self._word_is(self._peek(), "intersect"):
                self._next()
                right = self.parse_product()
                span = Span(self._span_start(left), self._span_end(right))
                left = nodes.Intersect(left=left, right=right, span=span)
            return left
        finally:
            self._leave()

    def parse_product(self) -> nodes.Expr:
        self._enter()
        try:
            left = self.parse_primary()
            while True:
                tok = self._peek()
                if self._word_is(tok, "times"):
                    self._next()
                    right = self.parse_primary()
                    span = Span(self._span_start(left), self._span_end(right))
                    left = nodes.Times(left=left, right=right, span=span)
                elif self._word_is(tok, "join") and self._peek(1).kind is TokenKind.LBRACKET:
                    self._next()  # join
                    self._expect(TokenKind.LBRACKET, "'['")
                    cond = self.parse_cond()
                    self._expect(TokenKind.RBRACKET, "']' to close '['")
                    right = self.parse_primary()
                    span = Span(self._span_start(left), self._span_end(right))
                    left = nodes.Join(cond=cond, left=left, right=right, span=span)
                else:
                    return left
        finally:
            self._leave()

    def parse_primary(self) -> nodes.Expr:
        self._enter()
        try:
            tok = self._peek()
            if tok.kind is TokenKind.LPAREN:
                open_tok = self._next()
                inner = self.parse_expr()
                self._expect_close(TokenKind.RPAREN, "')'", open_tok)
                return inner
            if (
                tok.kind is TokenKind.WORD
                and tok.text in UNARY_OPS
                and self._peek(1).kind is TokenKind.LBRACKET
            ):
                return self.parse_unary()
            if tok.kind is TokenKind.WORD:
                self._next()
                return nodes.Relation(name=tok.text, span=self._tok_span(tok))
            raise self._fail(
                f"expected a relation, '(' or an operator, found {self._describe(tok)}",
                tok,
            )
        finally:
            self._leave()

    def parse_unary(self) -> nodes.Expr:
        self._enter()
        try:
            op_tok = self._next()  # select | project | rename
            self._expect(TokenKind.LBRACKET, "'['")
            if op_tok.text == "select":
                cond = self.parse_cond()
                self._expect(TokenKind.RBRACKET, "']' to close '['")
                inner = self.parse_primary()
                return nodes.Select(
                    cond=cond, input=inner, span=Span(self._span_start_op(op_tok), inner.span.end)
                )
            if op_tok.text == "project":
                attrs = [self.parse_attr_ref()]
                while self._peek().kind is TokenKind.COMMA:
                    self._next()
                    attrs.append(self.parse_attr_ref())
                self._expect(TokenKind.RBRACKET, "']' to close '['")
                inner = self.parse_primary()
                return nodes.Project(
                    attrs=attrs, input=inner, span=Span(self._span_start_op(op_tok), inner.span.end)
                )
            # rename: [New] or [old->new, ...]
            rel_name, columns = self.parse_rename_spec()
            self._expect(TokenKind.RBRACKET, "']' to close '['")
            inner = self.parse_primary()
            return nodes.Rename(
                rel_name=rel_name,
                columns=columns,
                input=inner,
                span=Span(self._span_start_op(op_tok), inner.span.end),
            )
        finally:
            self._leave()

    def parse_rename_spec(self) -> tuple[str | None, list[tuple[nodes.AttrRef, str]]]:
        if self._peek().kind is TokenKind.WORD and self._peek(1).kind is TokenKind.ARROW:
            old = self.parse_attr_ref()
            self._next()  # ->
            new_tok = self._expect(TokenKind.WORD, "the new attribute name after '->'")
            columns = [(old, new_tok.text)]
            while self._peek().kind is TokenKind.COMMA:
                self._next()
                old = self.parse_attr_ref()
                self._next()  # ->
                new_tok = self._expect(TokenKind.WORD, "the new attribute name after '->'")
                columns.append((old, new_tok.text))
            return None, columns
        new_tok = self._expect(TokenKind.WORD, "the new relation name")
        return new_tok.text, []

    def parse_attr_ref(self) -> nodes.AttrRef:
        tok = self._expect(TokenKind.WORD, "an attribute name")
        if self._peek().kind is TokenKind.DOT:
            self._next()
            name_tok = self._expect(TokenKind.WORD, "an attribute name after '.'")
            return nodes.AttrRef(
                qualifier=tok.text,
                name=name_tok.text,
                span=Span(self._tok_span(tok).start, self._tok_span(name_tok).end),
            )
        return nodes.AttrRef(qualifier=None, name=tok.text, span=self._tok_span(tok))

    # -- conditions (GRAMMAR.md 1.5): cond > andcond > notcond > catom -------

    def parse_cond(self) -> nodes.Cond:
        self._enter()
        try:
            left = self.parse_andcond()
            while self._word_is(self._peek(), "or"):
                self._next()
                right = self.parse_andcond()
                span = Span(self._span_start(left), self._span_end(right))
                left = nodes.Or(left=left, right=right, span=span)
            return left
        finally:
            self._leave()

    def parse_andcond(self) -> nodes.Cond:
        self._enter()
        try:
            left = self.parse_notcond()
            while self._word_is(self._peek(), "and"):
                self._next()
                right = self.parse_notcond()
                span = Span(self._span_start(left), self._span_end(right))
                left = nodes.And(left=left, right=right, span=span)
            return left
        finally:
            self._leave()

    def parse_notcond(self) -> nodes.Cond:
        self._enter()
        try:
            # LL(2) per GRAMMAR.md 1.6: `not` negates only when the next token
            # starts a condition; followed by a comparison operator it is an
            # attribute reference named `not`.
            if self._word_is(self._peek(), "not") and self._peek(1).kind in (
                TokenKind.LPAREN,
                TokenKind.WORD,
                TokenKind.STRING,
                TokenKind.NUMBER,
            ):
                not_tok = self._next()
                child = self.parse_notcond()
                return nodes.Not(child=child, span=Span(self._pos(not_tok), child.span.end))
            return self.parse_catom()
        finally:
            self._leave()

    def parse_catom(self) -> nodes.Cond:
        self._enter()
        try:
            tok = self._peek()
            if tok.kind is TokenKind.LPAREN:
                open_tok = self._next()
                inner = self.parse_cond()
                self._expect_close(TokenKind.RPAREN, "')'", open_tok)
                return inner
            left = self.parse_operand()
            op_tok = self._expect(TokenKind.COMPARISON, "a comparison operator")
            right = self.parse_operand()
            span = Span(self._span_start(left), self._span_end(right))
            return nodes.Comparison(op=op_tok.text, left=left, right=right, span=span)
        finally:
            self._leave()

    def parse_operand(self) -> nodes.Operand:
        tok = self._peek()
        if tok.kind is TokenKind.WORD:
            self._next()
            if self._peek().kind is TokenKind.DOT:
                self._next()
                name_tok = self._expect(TokenKind.WORD, "an attribute name after '.'")
                return nodes.AttrRef(
                    qualifier=tok.text,
                    name=name_tok.text,
                    span=Span(self._tok_span(tok).start, self._tok_span(name_tok).end),
                )
            return nodes.AttrRef(qualifier=None, name=tok.text, span=self._tok_span(tok))
        if tok.kind is TokenKind.NUMBER:
            self._next()
            assert isinstance(tok.value, (int, Decimal))
            return nodes.Literal(value=tok.value, span=self._tok_span(tok))
        if tok.kind is TokenKind.STRING:
            self._next()
            assert isinstance(tok.value, str)
            return nodes.Literal(value=tok.value, span=self._tok_span(tok))
        raise self._fail(
            f"expected an attribute, number or string, found {self._describe(tok)}", tok
        )

    # -- span helpers -------------------------------------------------------

    def _span_start(self, node: nodes.Expr | nodes.Cond | nodes.Operand) -> Position:
        return node.span.start

    def _span_end(self, node: nodes.Expr | nodes.Cond | nodes.Operand) -> Position:
        return node.span.end

    def _span_start_op(self, tok: Token) -> Position:
        return self._pos(tok)


def parse(source: str, tokens: list[Token] | None = None) -> nodes.Query:
    """Parse a query; raises LexicalError/SyntaxError with positions on failure."""
    if tokens is None:
        tokens = _tokenize(source)
    return Parser(source, tokens).parse_query()
