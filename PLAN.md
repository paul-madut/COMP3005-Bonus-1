# Plan: Relational Algebra Engine (COMP 3005 Bonus 1)

Working plan for the project.
The dates are a guideline, not a contract.
What matters is the order: grammar before parser, parser before operators, operators before measurements.

## 0. Guiding principles

- **Language design first.** GRAMMAR.md is drafted before any parser code.
  The parser is a direct translation of the grammar: one function per grammar rule.
- **A DBMS pipeline, not a script.** Lexer, then parser (AST), then binder (semantic analysis), then executor.
  Later bonus projects plug in here: the SQL front end compiles into the same bound plan, the cost model reads the bound plan, and storage and indexes replace leaf and join operators.
- **Static checking before execution.** Name, schema and type errors are all found in the binder before a single tuple is touched.
  So `select[Age>'30'](R)` is a type error even when R is empty.
- **Every line must be explainable.** After each phase, do an explain-back of the module before moving on.

## 1. Key decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Language | Python 3.12, stdlib only for the engine. Dev tools (pytest, ruff, mypy, matplotlib) are managed by uv and never imported by the engine. |
| 2 | Precedence (low to high) | `union`, `minus` (level 1, left) < `intersect` (level 2, left) < `times`, `join[c]` (level 3, left) < prefix operators and atoms. Mirrors SQL (INTERSECT binds tighter than UNION/EXCEPT) and arithmetic. So `A union B minus C` = `(A union B) minus C` and `A minus B minus C` = `(A minus B) minus C`. **Confirm against Relax in Phase 1 and document any difference.** |
| 3 | Keywords vs identifiers (case 8) | Contextual keywords. The lexer emits only `WORD`, and the parser decides from position. In an operand position any word is an attribute. `select`/`project`/`rename` are operators only when followed by `[` (LL(2)). `not` is an attribute when followed by a comparison operator. Keywords are lowercase and case-sensitive. |
| 4 | Literals | Numbers are `-?digits(.digits)?`, stored exactly as `int` or `Decimal`, never `float`. A `-` must be immediately followed by a digit (case 4). `1x` is a lexical error, not two tokens. Strings in queries must be quoted, and a bare word is always an attribute (case 18). |
| 5 | Relation body values | The lexer has a separate "tuple body" mode inside `{ }`. A bare value is a run of characters up to `,`, whitespace, `(`, `)`, `'`, `{` or `}`. It is a number if it scans fully as one, otherwise a string. `'32'` is a string. Newlines end tuples. |
| 6 | Types | Two types, number and string, inferred per column at load. A mixed column is a type error at the definition line. Columns of an empty relation have type `unknown`, compatible with anything. |
| 7 | Attribute identity | Each attribute is `(qualifier, name, type)`. Base relations qualify with their own name. An unqualified reference must match exactly one attribute, otherwise it is an ambiguity error listing the candidates. |
| 8 | `times` collision | The same qualifier and name on both sides (for example `Emp times Emp`) is a schema error with the hint "use rename". This is the README argument for case 20. |
| 9 | Union compatibility | Same arity, same unqualified names in order, compatible types. The result takes the left schema, qualifiers included. |
| 10 | `project[Name, Name]` (case 24) | Schema error: duplicate output attribute. Keeps the invariant that every schema has unique qualified names. |
| 11 | Join implementation | Fused nested loop: evaluate the condition on `(left_row, right_row)` and concatenate only on a match. Never materialize the cross product. No dedup on join output, because distinct inputs give distinct concatenated pairs (prove it in the README). |
| 12 | Tuple equality and dedup | One explicit `tuple_key()` / `values_equal()` in `relalg/values.py` defines equality. Relations store tuples in an insertion-ordered dict keyed on that, which gives deterministic output order. |
| 13 | Execution model | Volcano-style iterators (Python generators). Each operator has a stats object (rows in, rows out, comparisons, time). `--stats` prints them in the style of EXPLAIN ANALYZE. |
| 14 | Statements in files | A file holds relation definitions plus optional queries terminated by `;`. A query given on the command line needs no `;`. |
| 15 | Comments | `//` only at the start of a line (after optional whitespace), so bare values like `a//b` are not broken. |

## 2. Repository layout

```
ra.py                  thin CLI: --db FILE, --tree, --stats, REPL if no query
relalg/
  errors.py            RAError + Lexical/Syntax/Name/Schema/Type, Span, caret rendering
  tokens.py            TokenKind, Token(kind, text, value, line, col, offset)
  lexer.py             hand-written scanner, query mode + tuple-body mode
  nodes.py             frozen dataclasses for the parse tree (expr + condition nodes, with spans)
  parser.py            recursive descent, one method per grammar rule
  tree_printer.py      box-drawing tree, conditions drawn as subtrees
  values.py            types, tuple_key, comparison semantics
  schema.py            Attribute, Schema, name resolution
  relation.py          schema + ordered set of tuples
  catalog.py           loads relation definitions
  binder.py            parse tree -> bound plan (indexes resolved, types checked)
  operators.py         the eight operators + counters
  executor.py          bottom-up evaluation
  formatter.py         table output (header always, "(0 tuples)" when empty)
bench/
  gen.py               data generator (n, m, match rate, seed)
  run_experiment.py    runs the sizes, writes CSV
  plot.py              matplotlib, report only
examples/              sample relation files (Section 4.1 data)
notes/                 scratch notes: AI mistakes, Relax observations
tests/                 pytest
GRAMMAR.md  REPORT.md  DESIGN_LOG.md  README.md  pyproject.toml
.github/workflows/ci.yml   ruff + mypy + pytest
```

## 3. Phases

The dates assume a start on Tue 2026-09-29 and are only a guideline.
If the deadline is closer, compress Phases 6 and 9 first and never compress Phase 2.

### Phase 1: Study, no code (Sep 29 to 30)

- Spend an hour in Relax (dbis-uibk.github.io/relax).
  Record in `notes/RELAX_NOTES.md` what it does with precedence, self joins, qualified names after a join, and dedup on project.
- Read: Crafting Interpreters chapters on scanning and parsing, Wikipedia on EBNF, recursive descent, maximal munch and operator precedence, and optionally Dragon Book sections 2.2 to 2.4 and 4.4.
- Set up the dev environment (`uv sync`) and start DESIGN_LOG.md.
- Keep `notes/AI_WRONG.md` open from day one and log every AI mistake as it happens.

### Phase 2: GRAMMAR.md draft (Oct 1)

- Full EBNF: program, definitions, tuple bodies, literals, expressions in three levels, conditions.

  ```
  expr      ::= setterm  { ("union" | "minus") setterm }
  setterm   ::= product  { "intersect" product }
  product   ::= primary  { "times" primary | "join" "[" cond "]" primary }
  primary   ::= unary | "(" expr ")" | WORD
  cond      ::= andcond { "or" andcond }
  andcond   ::= notcond { "and" notcond }
  notcond   ::= "not" notcond | catom
  catom     ::= "(" cond ")" | operand compop operand
  ```

- Add the precedence table, the contextual keyword rule, the lookahead points and a statement of the language generated.
- Ambiguity demonstration with concrete data:
  - Case 10: A={1}, B={2}, C={1}. `(A union B) minus C = {2}` but `A union (B minus C) = {1,2}`.
  - Case 11: A={1,2,3}, B={2}, C={1,2}. `(A minus B) minus C = {3}` but `A minus (B minus C) = {1,2,3}`.
- Explain why `Expr ::= Expr "union" ...` recurses forever in recursive descent, and point at the `{ }` repetitions that replace it.
  Left associativity comes from folding left inside the loop.

### Phase 3: Lexer (Oct 2 to 3), cases 1 to 9

- Character-by-character scanner with maximal munch for `<=`, `>=`, `!=`.
- Quoted strings with the `''` escape.
  An unterminated string, or a newline inside a string, is a lexical error at the opening quote.
- Every token carries offset, line and column.
  Test token streams directly, not only parse results.

### Phase 4: Parser, parse tree, tree printer (Oct 4 to 5), cases 10 to 17

- Errors render with a position and a caret:

  ```
  Syntax error at 1:17: expected ')' to close '(' opened at 1:15, found end of input
    select[Age>30](R
                    ^
  ```

- `--tree` prints without executing.
  Condition nodes are drawn as subtrees so the grouping in cases 12 and 13 is visible.
- Case 2 test: the parse tree equals case 1's with positions ignored, and the printed trees are byte-identical.

### Phase 5: Semantics (Oct 6 to 7), cases 18 to 25

- Values, schema, catalog, binder, operators, executor, formatter.
- Property tests on top of hand-computed cases:
  `A intersect B == A minus (A minus B)`, `join[c] == select[c](times)`, project is idempotent, union is commutative up to schema.

### Phase 6: Error hardening (Oct 8)

- All five categories, plus a last-resort "internal error" message instead of a traceback.
- Deep nesting (for example 5000 parentheses) gives a clean "nested too deeply" error instead of a RecursionError.
- CLI subprocess tests assert "Traceback" never appears.
- A hand-rolled fuzzer mutates valid queries (drop, duplicate, swap tokens and characters) and checks every result is either an answer or an RAError.
- Extra edge cases: `> =`, `<>`, `!` alone, `a>- 30`, `''`, trailing comma, arity mismatch, duplicate attribute or relation names, `Emp . DID`, `select[not=3]`, a relation named `union`.

### Phase 7: Generator and instrumentation (Oct 9)

- `bench/gen.py --n --m --match-rate k --seed` produces `R(a,b)` and `S(b,c)`.
- `a` and `c` are unique ids so no tuples collapse under set semantics.
  Otherwise the real n silently shrinks, which would break the Q1 formula.
- The `b` domain has size `m/k`, so each R tuple matches about k tuples of S and the output is about n times k.
- The join and select counters sit exactly at the condition evaluation call.
- Time with `perf_counter` around execution only, and report load time separately.
  Median of 3 runs for small n, one run for the largest.
  Record whether GC was disabled.

### Phase 8: Experiment and REPORT.md (Oct 10, start the large runs early in the background)

- Fill the table from 1000 to 64000.
  In Python, expect the 64000 join to take tens of minutes.
- Q1: comparisons = n times m exactly, asserted in the runner.
- Q2: least-squares slope of log t against log n, fitted on the larger points, expected close to 2.
- Q3: select and project have a slope close to 1.
  Project's constant includes the dedup hashing.
- Q4: `t(1e6) = t(64000) * (1e6/64000)^2 = t(64000) * 244.14`, cross-checked with per-comparison cost times 10^12.
- Q5: sweep k in {0, 1, 10, 100, 1000} at a fixed n.
  Comparisons stay constant while time grows with output construction.
- Q6: detect equi-joins and use a hash join (build on S.b, probe with R) for O(n+m).
  Mention sort-merge, index nested loop, Grace partitioning for memory, and constant-factor improvements.

### Phase 9: Finish GRAMMAR.md (Oct 11)

- Reconcile the document with what the parser really does.
  Every tree in the document should be pasted `--tree` output.

### Phase 10: Wrap-up (Oct 12 to 13)

- README: how to run, what is supported, limitations, the case 20 argument, the join no-dedup proof.
- Finish the design log from `notes/AI_WRONG.md` and the session notes.
- Rehearse the oral check.
- Record the roughly five-minute video: tree for case 10 or 11, one number from the report, a code tour.

## 4. Testing

- `tests/test_required.py` holds all 25 required cases, named `test_case_01` to `test_case_25` to match the assignment table.
  They start skipped and get enabled phase by phase.
- Per-module unit tests, property tests, CLI no-traceback tests and the fuzzer.
- CI runs ruff, mypy and pytest on every push.

## 5. Things only I can do

- The design log must describe real sessions, and the three AI mistakes must be real ones.
- The oral check: after each phase, explain the module back, and simplify anything that cannot be explained.
- The video.
