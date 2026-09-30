"""Table output: header always, "(0 tuples)" when empty."""

from __future__ import annotations

from .schema import Schema
from .values import Value


def format_table(schema: Schema, rows: list[tuple[Value, ...]]) -> str:
    """Render a relation as an aligned text table with a header row."""
    headers = schema.display()
    cells = [[repr(v) if isinstance(v, str) else str(v) for v in row] for row in rows]
    widths = [
        max(len(headers[i]), *(len(r[i]) for r in cells)) if cells else len(headers[i])
        for i in range(len(headers))
    ]

    def sep() -> str:
        return "+".join("-" * (w + 2) for w in widths)

    def fmt(row: list[str]) -> str:
        return "|".join(f" {cell:<{widths[i]}} " for i, cell in enumerate(row))

    lines = [fmt(headers), sep()]
    lines.extend(fmt(r) for r in cells)
    if not rows:
        lines.append("(0 tuples)")
    return "\n".join(lines)
