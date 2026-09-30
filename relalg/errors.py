"""RAError and its five categories, with source spans and caret rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    """A point in the source text: 1-based line and column, 0-based offset."""

    line: int
    col: int
    offset: int


@dataclass(frozen=True)
class Span:
    """A half-open region of source text, from start (inclusive) to end (exclusive)."""

    start: Position
    end: Position


class RAError(Exception):
    """Base class of every user-facing error.

    An RAError never carries a traceback to the user: the CLI catches it and
    renders the message, position and caret.  `span` is optional because some
    errors (for example a missing relation in the catalog) are easier to
    describe without one.
    """

    category = "error"

    def __init__(self, message: str, span: Span | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.span = span

    @property
    def line(self) -> int | None:
        return self.span.start.line if self.span else None

    @property
    def col(self) -> int | None:
        return self.span.start.col if self.span else None

    def render(self, source: str) -> str:
        """Render as 'Category at line:col: message' plus the source line and caret."""
        header = f"{self.category}: {self.message}"
        if self.span is None:
            return header
        line_no = self.span.start.line
        col = self.span.start.col
        source_lines = source.splitlines()
        header = f"{self.category} at {line_no}:{col}: {self.message}"
        if line_no < 1 or line_no > len(source_lines):
            return header
        text = source_lines[line_no - 1]
        length = max(self.span.end.offset - self.span.start.offset, 1)
        caret = " " * (col - 1) + "^" * min(length, max(len(text) - col + 1, 1))
        return f"{header}\n  {text}\n  {caret}"


class LexicalError(RAError):
    category = "Lexical error"


class SyntaxError(RAError):
    category = "Syntax error"


class NameError(RAError):
    category = "Name error"


class SchemaError(RAError):
    category = "Schema error"


class TypeError(RAError):
    category = "Type error"
