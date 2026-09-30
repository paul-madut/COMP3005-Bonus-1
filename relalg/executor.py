"""Bottom-up plan opening and the --stats report (decision 13)."""

from __future__ import annotations

from .operators import Row, Stats, execute
from .schema import Schema

__all__ = ["Row", "Schema", "Stats", "execute", "render_stats"]


def render_stats(stats: Stats) -> str:
    """Render the stats tree in the style of EXPLAIN ANALYZE."""

    lines: list[str] = []

    def walk(node: Stats, indent: str) -> None:
        parts = f"{node.label} (rows={node.rows_out}"
        if node.rows_in and node.rows_in != node.rows_out:
            parts += f", in={node.rows_in}"
        if node.comparisons:
            parts += f", comparisons={node.comparisons}"
        parts += f", time={node.time_ns / 1_000_000:.3f}ms)"
        lines.append(f"{indent}{parts}")
        for child in node.children:
            walk(child, indent + "  ")

    walk(stats, "")
    return "\n".join(lines)
