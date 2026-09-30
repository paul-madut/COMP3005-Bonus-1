# COMP3005 Bonus 1: Relational Algebra Engine

A relational algebra engine built from a hand-written grammar, tokenizer and recursive descent parser.
It is the first component of a larger DBMS.

## Status

All ten phases of PLAN.md are complete: grammar, lexer, parser, binder, operators, CLI,
hardening suite, benchmark harness, the reconciled GRAMMAR.md and the finished REPORT.md.
All 150 tests pass (including the 25 required cases), and ruff, `ruff format` and strict
mypy are clean.
See PLAN.md for the phased plan.

The performance study in REPORT.md is measured from a full 1000 → 64000 sweep
(`bench/results.csv`, ~48 min): the nested-loop join is quadratic (log-log slope 2.009)
and a one-million-tuple join would take about 5.6 days, which the hash join in Q6 brings
down to seconds.

What is left is human-only: the oral check and the video.
Four of the twelve Relax checklist questions (notes/RELAX_NOTES.md) are browser-only
observations about its result rendering; the precedence claims that GRAMMAR.md actually
depends on are confirmed against Relax's own grammar source.

## Requirements

- Python 3.12 or newer (the engine uses the standard library only)
- [uv](https://docs.astral.sh/uv/) for the development tools (pytest, ruff, mypy, matplotlib)

## Setup

```sh
uv sync
```

## Usage

```sh
# run a query against a file of relation definitions
python ra.py --db examples/employees.ra "project[Name](select[Age>30](Employees))"

# print the parse tree without executing
python ra.py --tree "A union B minus C"

# EXPLAIN ANALYZE-style per-operator statistics
python ra.py --db examples/employees.ra --stats \
  "select[Age>30](Employees) join[Employees.DID=Departments.DID] Departments"

# no query: interactive REPL (definitions and queries, one per line)
python ra.py --db examples/employees.ra
```

A relation file holds definitions and optional queries, each query ended by `;`:

```
Employees (EID, Name, Age) = {
  E1, John, 32
  E2, Alice, 28
}
project[Name](select[Age>30](Employees));
```

Every error - lexical, syntax, name, schema, type - is printed with its source
line, a caret and the position; no input ever produces a Python traceback.

## Development

```sh
uv run pytest
uv run ruff check .
uv run mypy
```

## Repository map

| Path | Contents |
|---|---|
| `GRAMMAR.md` | Grammar, precedence, ambiguity demonstration, parsing strategy, sources |
| `REPORT.md` | Performance study |
| `DESIGN_LOG.md` | Dated design diary |
| `PLAN.md` | Working plan |
| `ra.py`, `relalg/` | CLI and engine package |
| `bench/` | Data generator, experiment runner, plots |
| `tests/` | Test suite, including the 25 required cases |
| `examples/` | Sample relation files |

## Supported language

- **Unary operators:** `select[cond]`, `project[a, b, ...]`, `rename[New]` (rename the
  relation) and `rename[old->new, ...]` (rename columns).
- **Binary operators:** `union`, `minus`, `intersect`, `times`, `join[cond]`.
- **Conditions:** comparisons `= != < <= > >=` over qualified or unqualified attributes,
  numbers, quoted strings; combined with `and`, `or`, `not` and parentheses.
- **Precedence** (low to high): `union`/`minus` < `intersect` < `times`/`join` <
  prefix operators; in conditions `or` < `and` < `not` < comparison.
  Every binary level is left-associative (GRAMMAR.md §2).
- **Values:** exact `int` and `Decimal` numbers (never float), strings in single quotes
  with `''` for a literal quote, bare values inside relation bodies.
- **Definitions:** `Name (a, b) = { row … }`, types inferred per column at load;
  comments are `//` at line start.
- Keywords are contextual: in operand position any word is an attribute, so
  `union` can be a column name (case 8).

Not supported (see Known limitations): aggregation, sorting, outer/semi/anti joins.

## Design decisions

- **Grammar before parser.** GRAMMAR.md was drafted before any parser code and the
  parser is one function per grammar rule; phase 9 of the plan reconciled it against
  real `--tree` output, which is pasted into the document.
- **Static checking before execution.** The binder resolves every name, schema and type
  before a tuple is touched, so `select[Age>'30'](R)` is a type error even when `R` is
  empty (case 22).
- **Contextual keywords.** The lexer emits only `WORD`; the parser decides keyword-ness
  from position with at most two tokens of lookahead.
- **Set semantics throughout.** Relations are insertion-ordered sets keyed by an
  explicit `tuple_key()`; projection dedups, so `project[b](R)` is a set (decision 12).
- **A repeated projection attribute is an error** (case 24). `project[Name, Name](R)`
  reports a schema error, "duplicate output attribute", rather than emitting the column
  twice or silently collapsing it to one. The reason is that every other operator relies
  on a schema in which a qualified name identifies exactly one attribute: allowing
  `Name` twice would make `R.Name` ambiguous in any later `select` or `join` over the
  result. Erasing the duplicate instead would silently return a different arity than
  the query asked for, so the error is the honest option.
- **Fused nested loop join** (decision 11): the condition is evaluated on the pair and
  the concatenation is built only on a match - the cross product is never materialized.
  An equi-join is detected at bind time and the benchmark can switch to a hash join.
- **Volcano iterators.** Each operator is a Python generator with its own stats object
  (rows in, rows out, comparisons, time), printed by `--stats`.

## Why a self join needs rename

Case 20 asks for `rename[E2](Emp) join[Emp.MgrID=E2.EID] Emp`. Two earlier exits are
both closed:

1. `Emp times Emp` (and any un-renamed self join) is a **schema error**: both sides
   contribute the attribute `Emp.EID`, so the output would contain two attributes with
   the same qualified name - which would break the invariant that a schema identifies
   every attribute. The error message hints "use rename".
2. Writing the condition on one copy, `Emp join[Emp.MgrID=Emp.EID] Emp`, is *meaningless*
   before it is ever ambiguous: both sides are the same relation, so the condition
   compares a tuple with itself and the join degenerates to a filtered cross product
   over a single set of values.

`rename[E2]` gives the second copy a fresh qualifier: the condition can now say which
side it means (`Emp.MgrID = E2.EID`), and the output schema `E2.*` + `Emp.*` stays
unambiguous - case 19's distinction, in miniature.

## Why join output needs no dedup

Decision 11 says join output is not deduplicated. Proof that it cannot contain a
duplicate tuple:

The join emits `l ++ r` for pairs `(l, r)` with `l` a tuple of the left input and `r`
of the right. The left schema's arity `k` is fixed, so every emitted tuple splits
uniquely at position `k`: `t = l ++ r` forces `l = t[:k]` and `r = t[k:]`.
Therefore `l₁ ++ r₁ = l₂ ++ r₂` implies `l₁ = l₂` and `r₁ = r₂`, i.e. the pair is the
same - the concatenation map `(l, r) ↦ l ++ r` is injective on pairs of fixed arity.
Inputs are already sets (tuples dedup at load), so each pair is enumerated once, and
by injectivity each output tuple is produced once. ∎

(The proof needs both inputs to have a fixed arity, which every relation in this
engine has; it is exactly the same argument that makes `R times S` duplicate-free.)

## Known limitations

- No aggregation (γ), sorting (τ) or explicit dedup (∂) operator - projection's
  set semantics covers the dedup case (the plan's decision to drop ∂).
- Only θ/equi joins: no outer, semi or anti joins (Relax has them; see
  notes/RELAX_NOTES.md for the deliberate differences).
- `//` comments only at line start, strings may not span lines.
- No indexes or external-memory algorithms; the benchmark join is pure Python, which
  is why the 64000-row nested loop takes minutes (REPORT.md).
- Relax comparison: the precedence table is confirmed against Relax's own PEG grammar
  (`src/db/parser/grammar_ra.pegjs`), which states the same level ordering and folds
  binary operators left - see notes/RELAX_NOTES.md. Its *runtime* behaviours (result
  rendering, dedup display) were not exercised in the browser; nothing in this engine
  depends on them.
