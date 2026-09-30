"""Unit and property tests for the semantics layer (catalog, binder, executor).

Property tests sit on top of the hand-computed cases: the algebraic identities
must hold for arbitrary generated relations, not just the examples.
"""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from relalg.binder import Binder
from relalg.catalog import Catalog
from relalg.errors import NameError as RANameError
from relalg.errors import SchemaError as RASchemaError
from relalg.errors import TypeError as RATypeError
from relalg.executor import execute
from relalg.parser import parse
from relalg.values import tuple_key


def run(catalog: Catalog, query: str) -> list[tuple[int | Decimal | str, ...]]:
    plan = Binder(catalog).bind(parse(query))
    _, rows, _ = execute(plan)
    return list(rows)


def make_catalog(source: str) -> Catalog:
    c = Catalog()
    c.load(source)
    return c


DB = """
R (a, b) = {
  1, 'x'
  2, 'y'
  1, 'x'
}
S (a, b) = {
  3, 'z'
}
Empty (a, b) = {
}
T (b, c) = {
  1, 'p'
  2, 'q'
}
Numbers (n) = {
  5
  3
  5
  1
}
"""


# -- catalog / definitions ------------------------------------------------------


def test_definition_dedup_and_order() -> None:
    c = make_catalog(DB)
    # (1,'x') appears twice; set semantics collapse it, insertion order kept.
    assert c.rows("R") == [(1, "x"), (2, "y")]


def test_duplicate_relation_rejected() -> None:
    c = make_catalog(DB)
    with pytest.raises(RASchemaError):
        c.load("R (a) = {\n 1\n}")


def test_mixed_column_types_rejected() -> None:
    with pytest.raises(Exception, match="mixed column types"):
        make_catalog("M (a) = {\n 1\n 'x'\n}")


def test_quoted_number_is_string() -> None:
    c = make_catalog("Q (a) = {\n '32'\n}")
    assert c.rows("Q") == [("32",)]
    assert c.schema("Q").attrs[0].type.value == "string"


def test_empty_relation_unknown_type() -> None:
    c = make_catalog(DB)
    assert c.schema("Empty").attrs[0].type.value == "unknown"


def test_row_arity_mismatch_rejected() -> None:
    with pytest.raises(Exception, match="expected 2"):
        make_catalog("R (a, b) = {\n 1, 'x'\n 2\n}")


def test_duplicate_attribute_names_rejected() -> None:
    with pytest.raises(Exception, match="duplicate attribute"):
        make_catalog("R (a, a) = {\n 1, 2\n}")


# -- binder: static checking before execution -----------------------------------


def test_case_22_type_error_even_when_empty() -> None:
    # R has a numeric Age column; the *result* of the select is empty but the
    # comparison is still a type error, found at bind time before any execution.
    c = make_catalog("R (Age) = {\n 30\n}")
    with pytest.raises(RATypeError):
        run(c, "select[Age>'30'](R)")
    # A genuinely empty relation has unknown-typed columns, compatible with anything.
    c2 = make_catalog("R (Age) = {\n}")
    assert run(c2, "select[Age>'30'](R)") == []


def test_case_18_column_vs_column_not_string() -> None:
    # a=b compares the two columns; a=1 compares the column to the number.
    c = make_catalog("R (a, b) = {\n 1, 1\n 2, 2\n}")
    rows = run(c, "select[a=b](R)")
    assert rows == [(1, 1), (2, 2)]
    rows = run(c, "select[a=1](R)")
    assert rows == [(1, 1)]
    # '1' (a string literal) would be a type error against the number column.
    with pytest.raises(RATypeError):
        run(c, "select[a='1'](R)")


def test_case_21_union_schema_error() -> None:
    c = make_catalog(DB)
    with pytest.raises(RASchemaError):
        run(c, "R union T")
    # Same arity and names but crossed types is also a schema error.
    c2 = make_catalog(DB + "\nU (a, b) = {\n 1, 2\n}")
    with pytest.raises(RASchemaError):
        run(c2, "R union U")


def test_unknown_type_compatible_with_anything() -> None:
    c = make_catalog(DB)
    assert run(c, "Empty union R") == [(1, "x"), (2, "y")]
    assert run(c, "select[Empty.a=1](Empty union R)") == [(1, "x")]


def test_case_20_self_join_via_rename() -> None:
    c = make_catalog("E (id, mgr) = {\n 1, 1\n 2, 1\n}")
    rows = run(c, "rename[B](E) join[B.id=E.mgr] E")
    assert len(rows) == 2
    # Both DID-like columns stay distinguishable (case 19's property).
    with pytest.raises(RASchemaError):
        run(c, "E times E")


def test_case_19_join_keeps_both_columns() -> None:
    c = make_catalog(DB)
    rows = run(c, "R join[R.a=T.b] T")
    assert rows == [(1, "x", 1, "p"), (2, "y", 2, "q")]
    # The result schema holds both qualifiers.
    plan = Binder(c).bind(parse("R join[R.a=T.b] T"))
    from relalg.binder import schema_of

    names = [a.display() for a in schema_of(plan).attrs]
    assert names == ["R.a", "R.b", "T.b", "T.c"]


def test_case_24_duplicate_project_attribute() -> None:
    c = make_catalog(DB)
    with pytest.raises(RASchemaError):
        run(c, "project[a, a](R)")


def test_ambiguity_error_lists_candidates() -> None:
    c = make_catalog(DB)
    with pytest.raises(RASchemaError, match="R.b, T.b"):
        run(c, "select[b='x'](R join[R.a=T.b] T)")


def test_qualified_reference_resolves() -> None:
    c = make_catalog(DB)
    assert len(run(c, "select[T.b=1](R join[R.a=T.b] T)")) == 1


def test_unknown_relation_is_name_error() -> None:
    c = make_catalog(DB)
    with pytest.raises(RANameError):
        run(c, "select[a=1](Nope)")


# -- case 23 and 25: project dedup, empty output --------------------------------


def test_case_23_project_dedup() -> None:
    c = make_catalog(DB)
    rows = run(c, "project[a](R)")
    assert rows == [(1,), (2,)]  # two tuples, not three


def test_case_25_empty_output_prints_schema() -> None:
    c = make_catalog(DB)
    rows = run(c, "select[a=999](R)")
    assert rows == []
    from relalg.formatter import format_table

    out = format_table(
        Binder(c).bind(parse("select[a=999](R)")).schema
        if False
        else __import__("relalg.binder", fromlist=["schema_of"]).schema_of(
            Binder(c).bind(parse("select[a=999](R)"))
        ),
        [],
    )
    assert "(0 tuples)" in out
    assert "R.a" in out


# -- algebra identities (hand-computed) ------------------------------------------


def test_minus_and_intersect_sets() -> None:
    c = make_catalog("A (x) = {\n 1\n 2\n 3\n}\nB (x) = {\n 2\n}\nC (x) = {\n 1\n 2\n}")
    assert run(c, "A minus B minus C") == [(3,)]
    assert run(c, "A union B intersect C") == [(1,), (2,), (3,)]
    assert run(c, "(A union B) minus C") == [(3,)]
    assert run(c, "A intersect B") == [(2,)]


def test_join_equals_select_of_times() -> None:
    c = make_catalog("A (x) = {\n 1\n 2\n}\nB (y) = {\n 1\n 3\n}")
    joined = run(c, "A join[A.x=B.y] B")
    composed = run(c, "select[A.x=B.y](A times B)")
    assert joined == composed == [(1, 1)]


def test_project_idempotent() -> None:
    c = make_catalog(DB)
    once = run(c, "project[a](R)")
    twice = run(c, "project[a](project[a](R))")
    assert once == twice


def test_union_commutative_as_sets() -> None:
    c = make_catalog(DB)
    a = sorted(map(tuple_key, run(c, "R union S")))
    b = sorted(map(tuple_key, run(c, "S union R")))
    assert a == b


# -- property tests with generated relations --------------------------------------


def _random_relation(rng: random.Random, name: str, n: int) -> str:
    values = [(rng.randrange(3), rng.choice(["p", "q"])) for _ in range(n)]
    rows = "\n".join(f"  {a}, '{b}'" for a, b in values)
    return f"{name} (x, y) = {{\n{rows}\n}}"


def test_properties_hold_for_random_relations() -> None:
    rng = random.Random(42)
    for _ in range(20):
        src = _random_relation(rng, "A", 8) + "\n" + _random_relation(rng, "B", 6)
        c = make_catalog(src)
        a = sorted(map(str, map(tuple_key, run(c, "A"))))
        b = sorted(map(str, map(tuple_key, run(c, "B"))))

        # De Morgan for sets: A - B == A - (A & B)
        left = sorted(map(str, map(tuple_key, run(c, "A minus B"))))
        right = sorted(map(str, map(tuple_key, run(c, "A minus (A intersect B)"))))
        assert left == right

        # Absorption: A & (A u B) == A
        assert sorted(map(str, map(tuple_key, run(c, "A intersect (A union B)")))) == a

        # Commutativity of union (as sets, ignoring order)
        assert sorted(map(str, map(tuple_key, run(c, "A union B")))) == sorted(set(a) | set(b))

        # join[c] == select[c](times)
        assert sorted(map(str, run(c, "A join[A.x=B.x] B"))) == sorted(
            map(str, run(c, "select[A.x=B.x](A times B)"))
        )


# -- stats (--stats output, decision 13) ---------------------------------------------


def test_stats_rows_in_and_out() -> None:
    """Truthful counters: rows_out counts emitted tuples only, rows_in counts
    consumed input, and the plan root totals what the caller pulled."""
    c = make_catalog(DB)
    _, rows, stats = execute(Binder(c).bind(parse("select[a=1](R)")))
    out = list(rows)
    assert stats.label == "plan"
    assert stats.rows_out == len(out) == 1  # R dedups to 2 rows at load
    sel = stats.children[0]
    assert sel.label == "select"
    assert sel.rows_out == 1
    assert sel.rows_in == 2
    assert sel.comparisons == 2
    scan = sel.children[0]
    assert scan.label == "scan R"
    assert scan.rows_out == 2


@pytest.mark.parametrize(("n", "m"), [(3, 5), (5, 3)])
def test_nested_loop_comparisons_are_exactly_n_times_m(n: int, m: int) -> None:
    """REPORT.md Q1: the condition is evaluated once per pair, so the count is
    |R| * |S| regardless of which side is the outer relation."""
    c = make_catalog(
        "L (a) = {\n"
        + "\n".join(f"  {i}" for i in range(n))
        + "\n}\n"
        + "Rt (b) = {\n"
        + "\n".join(f"  {i}" for i in range(m))
        + "\n}"
    )
    _, rows, stats = execute(Binder(c).bind(parse("L join[L.a=Rt.b] Rt")))
    emitted = len(list(rows))
    join = stats.children[0]
    assert join.label == "join"
    assert join.comparisons == n * m, f"expected {n * m} comparisons, got {join.comparisons}"
    assert emitted == min(n, m)  # matches vary; the comparison count does not


def test_values_render_in_this_language_not_python() -> None:
    """Output and error messages must never leak Python's repr.

    `repr` renders a Decimal as `Decimal('1.5')` and switches to double quotes
    for a string containing a quote, so both are formatted explicitly instead.
    """
    from relalg.values import format_value

    assert format_value(Decimal("1.5")) == "1.5"
    assert format_value(30) == "30"
    # Strings round-trip into the relation-file syntax of section 4.1.
    assert format_value("O'Brien") == "'O''Brien'"
    assert format_value("has, comma") == "'has, comma'"


def test_decimal_literal_in_a_type_error_reads_as_written() -> None:
    c = make_catalog("N (s) = {\n  hello\n}")
    with pytest.raises(RATypeError) as e:
        run(c, "select[s>1.5](N)")
    assert "1.5" in str(e.value)
    assert "Decimal" not in str(e.value)
