"""Renders a parse tree as an indented box-drawing tree without executing it."""

from __future__ import annotations

from decimal import Decimal

from . import nodes

CONT_LAST = "   "
CONT_MID = "│  "
BRANCH_LAST = "└─ "
BRANCH_MID = "├─ "


def print_tree(node: nodes.Expr | nodes.Cond | nodes.Operand) -> str:
    """Render a parse-tree node as a multi-line box-drawing string."""
    return "\n".join(_render(node))


def _draw_children(children: list[list[str]]) -> list[str]:
    lines: list[str] = []
    for idx, child in enumerate(children):
        last = idx == len(children) - 1
        branch = BRANCH_LAST if last else BRANCH_MID
        cont = CONT_LAST if last else CONT_MID
        for j, line in enumerate(child):
            lines.append((branch if j == 0 else cont) + line)
    return lines


def _render(node: nodes.Expr | nodes.Cond | nodes.Operand) -> list[str]:
    match node:
        case nodes.Relation(name=name):
            return [name]
        case nodes.Select(cond=cond, input=inp):
            return ["select", *_draw_children([_render(cond), _render(inp)])]
        case nodes.Project(attrs=attrs, input=inp):
            parts = [_render(a) for a in attrs] + [_render(inp)]
            return ["project", *_draw_children(parts)]
        case nodes.Rename(rel_name=rel_name, columns=columns, input=inp):
            if rel_name is not None:
                label = f"rename[{rel_name}]"
            else:
                spec = ", ".join(f"{_attr_text(old)}->{new}" for old, new in columns)
                label = f"rename[{spec}]"
            return [label, *_draw_children([_render(inp)])]
        case nodes.Union(left=left, right=right):
            return ["union", *_draw_children([_render(left), _render(right)])]
        case nodes.Minus(left=left, right=right):
            return ["minus", *_draw_children([_render(left), _render(right)])]
        case nodes.Intersect(left=left, right=right):
            return ["intersect", *_draw_children([_render(left), _render(right)])]
        case nodes.Times(left=left, right=right):
            return ["times", *_draw_children([_render(left), _render(right)])]
        case nodes.Join(cond=cond, left=left, right=right):
            return ["join", *_draw_children([_render(cond), _render(left), _render(right)])]
        case nodes.And(left=left, right=right):
            return ["and", *_draw_children([_render(left), _render(right)])]
        case nodes.Or(left=left, right=right):
            return ["or", *_draw_children([_render(left), _render(right)])]
        case nodes.Not(child=child):
            return ["not", *_draw_children([_render(child)])]
        case nodes.Comparison(op=op, left=left, right=right):
            return [f"{_operand_text(left)} {op} {_operand_text(right)}"]
        case nodes.AttrRef(qualifier=q, name=name):
            return [f"{q}.{name}" if q else name]
        case nodes.Literal(value=value):
            return [_literal_text(value)]
    raise AssertionError(f"unhandled node {node!r}")  # pragma: no cover


def _operand_text(node: nodes.Operand) -> str:
    match node:
        case nodes.AttrRef(qualifier=q, name=name):
            return f"{q}.{name}" if q else name
        case nodes.Literal(value=value):
            return _literal_text(value)
    raise AssertionError(f"unhandled operand {node!r}")  # pragma: no cover


def _literal_text(value: int | Decimal | str) -> str:
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def _attr_text(ref: nodes.AttrRef) -> str:
    return f"{ref.qualifier}.{ref.name}" if ref.qualifier else ref.name
