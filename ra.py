#!/usr/bin/env python3
"""ra.py - the CLI: --db FILE, --tree, --stats, and a REPL when no query is given."""

from __future__ import annotations

import argparse
import sys

from relalg.binder import Binder
from relalg.catalog import Catalog
from relalg.errors import RAError
from relalg.executor import execute, render_stats
from relalg.formatter import format_table
from relalg.nodes import Query
from relalg.parser import parse
from relalg.tree_printer import print_tree


def _execute(catalog: Catalog, query: Query, stats: bool) -> None:
    """Bind and run one parsed query, printing its result table."""
    plan = Binder(catalog).bind(query)
    schema, rows, st = execute(plan)
    out = format_table(schema, list(rows))
    print(out)
    if stats:
        print()
        print(render_stats(st))


def _run_query(catalog: Catalog, text: str, tree: bool, stats: bool) -> None:
    """Parse a query, then print its tree or execute it."""
    query = parse(text)
    if tree:
        print(print_tree(query.expr))
        return
    _execute(catalog, query, stats)


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except RAError as e:
        # Already rendered by inner handlers; belt and suspenders.
        print(e.render(""), file=sys.stderr)
        return 1
    except RecursionError:
        print("error: expression nested too deeply", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 - last resort, never a traceback
        print(f"internal error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ra", description="relational algebra engine")
    ap.add_argument("--db", metavar="FILE", help="a file of relation definitions")
    ap.add_argument("--tree", action="store_true", help="print the parse tree, don't run")
    ap.add_argument("--stats", action="store_true", help="print per-operator statistics")
    ap.add_argument("query", nargs="?", help="a query; omit it to enter the REPL")
    args = ap.parse_args(argv)

    catalog = Catalog()
    if args.db:
        try:
            with open(args.db, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"error: cannot read {args.db}: {e.strerror}", file=sys.stderr)
            return 1
        try:
            catalog.load(text)
        except RAError as e:
            print(e.render(text), file=sys.stderr)
            return 1
        # Decision 14: a `;`-terminated query in the file runs and prints its
        # result, like a statement in a script.  `--tree` means "don't run",
        # so file queries are skipped there too.
        if not args.tree:
            try:
                for st in catalog.queries:
                    _execute(catalog, st.query, args.stats)
            except RAError as e:
                print(e.render(text), file=sys.stderr)
                return 1

    if args.query is not None:
        try:
            _run_query(catalog, args.query, args.tree, args.stats)
        except RAError as e:
            print(e.render(args.query), file=sys.stderr)
            return 1
        return 0

    return _repl(catalog, args.tree, args.stats)


def _read_or_empty(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _repl(catalog: Catalog, tree: bool, stats: bool) -> int:
    """Read statements until EOF. Definitions persist; queries print tables."""
    print("relational algebra REPL -- one statement per line, Ctrl-D to exit")
    buffer = ""
    while True:
        try:
            prompt = "... " if buffer else "ra> "
            line = input(prompt)
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            buffer = ""
            continue
        buffer += line
        if not buffer.strip():
            buffer = ""
            continue
        # A statement ends when the braces balance (definitions) or at once.
        if buffer.count("{") > buffer.count("}"):
            buffer += "\n"
            continue
        statement, buffer = buffer, ""
        if _ends_with_definition_body(statement):
            try:
                catalog.load_statement(statement)
            except RAError as e:
                print(e.render(statement), file=sys.stderr)
            continue
        try:
            _run_query(catalog, statement, tree, stats)
        except RAError as e:
            print(e.render(statement), file=sys.stderr)


def _ends_with_definition_body(text: str) -> bool:
    stripped = text.strip()
    i = 0
    while i < len(stripped) and (stripped[i].isalnum() or stripped[i] == "_"):
        i += 1
    head = stripped[i:].lstrip()
    return head.startswith("=") or head.startswith("(")


if __name__ == "__main__":
    sys.exit(main())
