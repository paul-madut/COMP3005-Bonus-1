"""Phase 6: hardening.

- CLI subprocess tests: no input may ever produce a Python traceback.
- The hand-rolled fuzzer: every mutated input yields an answer or an RAError.
- Deep nesting: a clean error instead of RecursionError.
- The extra edge cases from the plan: `> =`, `<>`, `!` alone, `''`, trailing
  commas, arity mismatches, `Emp . DID`, `select[not=3]`, a relation named
  `union`.
"""

from __future__ import annotations

import random
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from relalg.binder import Binder
from relalg.catalog import Catalog
from relalg.errors import LexicalError, NameError, RAError
from relalg.errors import SyntaxError as RASyntaxError
from relalg.executor import execute
from relalg.lexer import tokenize
from relalg.parser import parse

DB = """
R (a, b) = {
  1, 'x'
  2, 'y'
}
S (a, b) = {
  3, 'z'
}
Empty (a, b) = {
}
union (x) = {
  1
}
"""


def run_query(query: str) -> list[tuple[int | Decimal | str, ...]]:
    c = Catalog()
    c.load(DB)
    _, rows, _ = execute(Binder(c).bind(parse(query)))
    return list(rows)


# -- CLI: never a traceback ------------------------------------------------------

CLI_CASES = [
    "select[Age>30](R",  # syntax error
    "select[Nope=1](R)",  # name error
    "R union Nope",  # name error in operand
    "select[a>'30'](R)",  # type error
    "R times R",  # schema collision
    "select[a=1](R))",  # trailing junk
    "",  # empty query
    "((((",  # unbalanced
    "select[a=1](R) garbage",  # junk after query
    "'unterminated",  # lexical error
    "select[a!1](R)",  # bad bang
    "project[](R)",  # empty list
    "select[1=1](R)",  # two literals: grammatical, rejected at bind time
]


def test_file_query_runs_but_not_under_tree(tmp_path: Path) -> None:
    """Decision 14: a `;`-terminated query in a `--db` file executes and
    prints, before any command-line query; `--tree` means nothing runs."""
    db = tmp_path / "queries.ra"
    db.write_text(
        "R (a, b) = {\n  1, 'x'\n  2, 'y'\n}\nproject[a](select[a=2](R));\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "ra.py", "--db", str(db), "select[a=1](R)"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert proc.returncode == 0, proc.stderr
    # The file's single-column table comes first, the CLI query's after it.
    assert " R.a \n" in proc.stdout  # header of project[a](...)
    assert " 2   " in proc.stdout  # its one row
    assert "R.a | R.b" in proc.stdout  # the command-line query's header
    assert proc.stdout.index(" R.a \n") < proc.stdout.index("R.a | R.b")

    # --tree: "print the parse tree, don't run" - the file query stays silent.
    proc = subprocess.run(
        [sys.executable, "ra.py", "--db", str(db), "--tree", "R"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert proc.returncode == 0, proc.stderr
    assert " R.a \n" not in proc.stdout
    assert " 2   " not in proc.stdout


@pytest.mark.parametrize("query", CLI_CASES)
def test_cli_never_prints_traceback(query: str) -> None:
    proc = subprocess.run(
        [sys.executable, "ra.py", "--db", "examples/hardening.ra", query],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert "Traceback" not in proc.stderr, proc.stderr
    assert proc.returncode in (0, 1)
    if proc.returncode == 1:
        assert proc.stderr.strip(), "an error must print a message"


def test_cli_missing_db_file() -> None:
    proc = subprocess.run(
        [sys.executable, "ra.py", "--db", "no/such/file.ra", "R"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert "Traceback" not in proc.stderr
    assert proc.returncode == 1
    assert "cannot read" in proc.stderr


def test_cli_deep_nesting_is_clean() -> None:
    query = "select[a=1](" * 2500 + "R" + ")" * 2500
    proc = subprocess.run(
        [sys.executable, "ra.py", "--db", "examples/hardening.ra", query],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert "Traceback" not in proc.stderr
    assert "nested too deeply" in (proc.stderr + proc.stdout)


def test_cli_tree_flag_does_not_execute() -> None:
    proc = subprocess.run(
        [sys.executable, "ra.py", "--db", "examples/hardening.ra", "--tree", "R union S"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert proc.returncode == 0
    assert "union" in proc.stdout
    # A name error must not fire under --tree (no binding happened).
    proc = subprocess.run(
        [sys.executable, "ra.py", "--db", "examples/hardening.ra", "--tree", "Nope"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert proc.returncode == 0


# -- the fuzzer --------------------------------------------------------------------


VALID_SEEDS = [
    "select[a=1](R)",
    "project[a, b](R)",
    "R union S",
    "R minus S",
    "R intersect S",
    "R times S",
    "R join[R.a=S.a] S",
    "rename[T](R)",
    "rename[a->c](R)",
    "select[a=1 and b='x' or not a=2](R)",
    "(R union S) times R",
    "select[a>=1](Empty)",
]


def _mutate(rng: random.Random, text: str) -> str:
    ops = ["drop", "dup", "swap", "char", "insert"]
    op = rng.choice(ops)
    if not text:
        return "x"
    i = rng.randrange(len(text))
    if op == "drop":
        return text[:i] + text[i + 1 :]
    if op == "dup":
        return text[:i] + text[i] + text[i:]
    if op == "swap" and i + 1 < len(text):
        return text[:i] + text[i + 1] + text[i] + text[i + 2 :]
    if op == "char":
        repl = rng.choice("()[]',=<>!abz015-{} .;")
        return text[:i] + repl + text[i + 1 :]
    # insert
    return text[:i] + rng.choice("()[]',=<>!abz015-{} .;") + text[i:]


def test_fuzzer_always_answer_or_raerror() -> None:
    """Every mutated input either answers or raises RAError - never anything else."""
    rng = random.Random(7)
    c = Catalog()
    c.load(DB)
    checked = 0
    for seed in VALID_SEEDS:
        text = seed
        for _ in range(60):
            text = _mutate(rng, text)
            try:
                query = parse(text)
                plan = Binder(c).bind(query)
                _, rows, _ = execute(plan)
                list(rows)  # drain
            except RAError:
                pass  # expected: the fuzzer cares that nothing else escapes
            checked += 1
    assert checked == len(VALID_SEEDS) * 60


def test_fuzzer_lexical_never_other_exception() -> None:
    rng = random.Random(11)
    for _ in range(500):
        text = _mutate(rng, rng.choice(VALID_SEEDS))
        try:
            tokenize(text)
        except LexicalError:
            continue
        except Exception as e:  # noqa: BLE001
            pytest.fail(f"lexer raised {type(e).__name__} on {text!r}")


def test_two_literal_comparison_is_answer_or_raerror() -> None:
    """`select[1=1](R)` parses - GRAMMAR 1.5 allows literals as operands - so
    the binder must reject it with an RAError, never an AssertionError.  This
    is the input the fuzzer's answer-or-RAError property was one character
    mutation away from generating, and it used to escape as an internal error."""
    c = Catalog()
    c.load(DB)
    for text in ("select[1=1](R)", "select['a'<'b'](R)", "select[1=1 or a=1](R)"):
        try:
            plan = Binder(c).bind(parse(text))
            list(execute(plan)[1])
        except RAError:
            continue
        pytest.fail(f"{text} must be rejected with an RAError")


# -- the plan's edge cases -----------------------------------------------------------


def test_gt_space_eq_is_two_comparisons() -> None:
    with pytest.raises(RASyntaxError):
        parse("select[a> =1](R)")  # two operators, no operand between


def test_lt_gt_is_not_an_operator() -> None:
    with pytest.raises(Exception):  # noqa: B017 - parser or binder, but never silent
        run_query("select[a<>1](R)")


def test_bang_alone_is_lexical_error() -> None:
    with pytest.raises(LexicalError):
        tokenize("select[a!1](R)")


def test_empty_string_literal() -> None:
    c = Catalog()
    c.load(DB + "\nT (s) = {\n 'a'\n ''\n}")
    assert run_query("select[b=''](R)") == []
    _, rows, _ = execute(Binder(c).bind(parse("select[s=''](T)")))
    assert list(rows) == [("",)]


def test_trailing_comma_in_attrlist() -> None:
    with pytest.raises(RASyntaxError):
        parse("project[a,](R)")


def test_arity_mismatch_in_definition() -> None:
    with pytest.raises(RASyntaxError):
        Catalog().load("R (a, b) = {\n 1\n}")


def test_qualified_ref_with_space() -> None:
    """`Emp . DID` is one attribute reference, whitespace notwithstanding."""
    expr = parse("select[R . a=1](R)").expr
    assert type(expr).__name__ == "Select"


def test_select_not_equals_reads_not_as_attribute() -> None:
    """`select[not=3]` follows GRAMMAR.md 1.6: `not` followed by a comparison
    operator is an attribute reference, so it parses, then the binder reports
    the (missing) attribute by name."""
    expr = parse("select[not=3](R)").expr
    assert type(expr).__name__ == "Select"
    c = Catalog()
    c.load(DB)
    with pytest.raises(NameError, match="not"):
        Binder(c).bind(parse("select[not=3](R)"))


def test_relation_named_union() -> None:
    """A relation literally named `union` works everywhere (case 8's cousin)."""
    assert run_query("select[x=1](union)") == [(1,)]
    assert run_query("union") == [(1,)]


def test_semicolon_terminated_query_in_file() -> None:
    c = Catalog()
    c.load("R (a) = {\n 1\n}\nselect[a=1](R);")
    assert len(c.queries) == 1
