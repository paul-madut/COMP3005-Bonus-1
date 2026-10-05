# Design log

One short entry per working session, dated.
Each entry says what I was trying to do, what I tried, and what broke.
At least three entries describe a specific occasion where AI assistance gave something wrong, slow or incomplete, what the problem was, and how I found it (raw notes live in `notes/AI_WRONG.md`).

## Entry template

```
## YYYY-MM-DD

**Goal:**
**Tried:**
**What broke:**
**AI was wrong (if any):**
**Next:**
```

## 2026-09-29

**Goal:** Understand the assignment and plan the work before writing any code.
**Tried:** Read the spec end to end and drafted a phased plan (PLAN.md).
Chose Python 3.12 with a stdlib-only engine.
Set up the repository skeleton.
**What broke:** The first layout had the CLI as `ra.py` next to a package directory `ra/`, and mypy refused to run ("Duplicate module named ra").
Two things claiming the same module name would also make `import ra` ambiguous from inside the CLI, so the package became `relalg/` and `ra.py` stays as the command from the spec.
**AI was wrong (if any):**
**Next:** Explore Relax, read on grammars and recursive descent, then draft GRAMMAR.md.

## 2026-09-29 (2)

**Goal:** Phase 1 (study) and Phase 2 (grammar draft): verify Relax facts, then write GRAMMAR.md before any parser code.
**Tried:** `uv sync` (env green: 25 cases skipped, ruff + strict mypy clean).
Researched the Relax repo itself instead of only planning to poke at the web app:
fetched its README, package.json and locales. Then drafted the full EBNF into GRAMMAR.md
with the precedence table, the contextual-keyword rule (LL(2)), the ambiguity
demonstration on concrete data and the parsing-strategy section.
**What broke:** The paths I expected in the Relax repo do not exist - no
`doc/lang/en/relax-guide.md`, no `src/calc2/parser/`. The real structure puts the PEG
grammar behind a pegjs-loader and the whole help text inside a generated `help.tsx`.
**AI was wrong (if any):** It invented a source layout for Relax (see
notes/AI_WRONG.md, "hallucinated Relax source layout"). Useful evidence I did find:
Relax parses with PEG.js, and `src/locales/en.json` contains its full operator toolbar
and error catalogue - which incidentally confirms several of my semantic choices
(type comparison errors, ambiguous columns, duplicate attributes rejected).
**Next:** Do the 12-step Relax browser session from notes/RELAX_NOTES.md, record the
results in the session log, reconcile any precedence difference into GRAMMAR.md §2,
then start Phase 3 (lexer).

## 2026-09-29 (3)

**Goal:** Phases 3–4 - the lexer and the recursive descent parser, each a direct
translation of one GRAMMAR.md section, plus the token-stream and tree tests
(required cases 1–17).
**Tried:** errors.py, tokens.py, the character-by-character lexer with its query and
tuple-body modes; then nodes.py and parser.py with one method per grammar rule,
and the box-drawing tree printer behind `--tree`.
**What broke:** Several things, in order: the ARROW edit into tokens.py swallowed the
newline before `LPAREN = auto()`, so the enum member vanished inside a comment and
mypy/pytest failed until I read the file back; case 16's error had to name where the
missing `(` was opened, which meant threading the opening token through
`_expect_close`; and a first pass of test expectations was simply wrong (off-by-one
token indexes, a wrong column) - the tests, not the lexer, were revised after checking
them against GRAMMAR.md line by line.
**AI was wrong (if any):** The first write of tests/test_lexer.py came back as
placeholder junk instead of the requested tests (see notes/AI_WRONG.md, "file writes
came back as placeholder junk"). Caught by reading the file back before running it.
**Next:** Phase 5 - values, schema, relation, catalog, binder, operators, executor.

## 2026-09-29 (4)

**Goal:** Phases 5–6 - the semantics layer (catalog → binder → operators → executor →
formatter → CLI) with all 25 required cases enabled, then hardening (no-traceback CLI
tests, the mutation fuzzer, depth limits, the edge-case list).
**Tried:** Static checking in the binder so name/schema/type errors fire before any
tuple is read; eight operators as Volcano generators with per-operator stats; `ra.py`
with `--db`, `--tree`, `--stats` and a REPL. Then the fuzzer and 12 CLI subprocess
cases asserting no input ever yields a Python traceback.
**What broke:** Empty-bodied definitions (`Empty (a, b) = {}`) crashed on an empty
col_types list; the file loader dropped the token before `;` when slicing a query out
of a file, and query bodies never saw an EOF token, so a trailing `)` was "garbage";
dedup only happened at execute time, so loading the same relation twice changed
answers - it moved into `Catalog.add`. Each was found by a failing required case or a
smoke run, not by inspection.
**AI was wrong (if any):** The hash-join path for Q6 keyed its buckets on the wrong
row coordinates and silently returned wrong pairs (see notes/AI_WRONG.md, "hash join
keyed on the wrong coordinates"). Found only by diffing it against the nested loop -
no test covered a second join strategy, which is now a rule: alternative strategies
differentially tested.
**Next:** Phase 7 - the data generator and the Q6 instrumentation.

## 2026-09-29 (5)

**Goal:** Phases 7–9 - bench/gen.py with controlled match rate, the experiment runner
and plots, then reconcile GRAMMAR.md with the parser that actually got written.
**Tried:** Generator verified against n·k output size and n·m comparison counts;
the runner asserts Q1 (`comparisons == n*m`) per row; equi-join detection in the
binder feeding a hash strategy for Q6; the full 1000→64000 sweep launched detached in
the background. Phase 9 pasted real `--tree` output into every tree in GRAMMAR.md.
**What broke:** Two doc↔parser mismatches surfaced by reading the rules against the
code: §1.4 claimed a unary operator's argument is `"(" expr ")"` when the parser takes
a `primary` (so `select[a=1]R` works), and §1.6's LL(2) rule for `not` was not
implemented - `parse_notcond` always negated, so `select[not=3]` errored instead of
reading `not` as an attribute. Since GRAMMAR.md is the spec, the parser was fixed for
the second and the document for the first. Also: `--stats` reported `rows=0` on the
root plan node (nothing counted it) and lumped rows-read into `rows_out`; Stats now
carries `rows_in` per decision 13. The background run died twice - a shell-launched
`&` process is killed with the tool call - before a Python double-fork daemonized it.
**AI was wrong (if any):** The runner rewrite for the loop-binding lint errors produced
object-typed getattr plumbing where the `BoundNode` union made a typed match obvious -
ruff and mypy had to flag it before it was rewritten cleanly (slow, not wrong).
**Next:** REPORT.md from results.csv once the sweep finishes, README wrap-up, final
pytest/ruff/mypy run.

## 2026-09-30

**Goal:** Phase 10 - write REPORT.md from the finished sweep, close the Relax precedence
question, and get the repository into a submittable state.
**Tried:** Read `bench/results.csv` before trusting it, which turned out to be the right
order. Two defects were in the data, not the prose: `gen.py` treated `--match-rate 0` as
`b_domain = max(m, 1)`, which is the *same* domain expression as `k=1`, so the k=0 row was
a duplicate of k=1 (8057 output rows) rather than the zero-output baseline Q5 needs; and
the committed `hash_join` row claimed 64000 output rows against the nested loop's 64033.
Fixed k=0 to draw the two `b` domains disjointly, then re-ran the whole 1000→64000 sweep
(~48 min) so the report quotes one internally consistent dataset with every assert live,
rather than a hand-patched CSV. Then wrote REPORT.md and verified it with a script that
re-extracts every quoted number from the CSV.
**What broke:** The hash/nested mismatch looked like a wrong hash join, which would have
invalidated Q6. It was not: running both strategies at n=64000 gave 64033 either way, and
the 64000 in the CSV was stale output from an older version of the runner (the run log
still showed a different nested time and no `out=` field, which is what gave it away).
The real defect was that nothing had ever *tested* the hash join - the equivalence check
existed only as an assert inside the benchmark, and the previous session's own recorded
lesson ("a second strategy needs its own equivalence test") had never been implemented.
Also found while writing Q4 that the plan's two cross-checks for t(10⁶) are algebraically
the same formula, so their agreement proves nothing; replaced it with per-comparison cost
measured at each size independently, which does cross-check (129-134 h for n ≥ 4000).
**AI was wrong (if any):** The 2026-09-29 entry concluded Relax's PEG grammar was not
available as a file after guessing `src/calc2/parser/` and getting 404s. That conclusion
was wrong: the grammar is at `src/db/parser/grammar_ra.pegjs`, found by listing the repo
tree with the GitHub API and grepping the paths instead of guessing another path. It
states Relax's precedence in a comment (union/difference loosest, then intersect, then
the joins, then unary, then atoms) and its `buildBinary` folds left, which confirms
decision 2 and required cases 10 and 11 from source rather than from browser behaviour.
Logged in notes/AI_WRONG.md as a follow-up; the lesson is to enumerate the tree before
concluding a file does not exist.
**Next:** Nothing in code. Rehearse the oral check and record the video.

## 2026-10-05

**Goal:** Pre-PR correctness audit: verify relalg/ against decisions 11-15 and the 25
required cases, then fix whatever the audit could substantiate and leave the tree green.
**Tried:** Evidence-first audit - read the parser, operators, values, lexer and binder
against the decisions table and probed the CLI instead of trusting the green suite.
Decision 11's fused loop with no dedup on join output, 12's single `tuple_key`, 13's
Volcano generators with rows_in/rows_out/comparisons/time, 14's `;`-terminated
statements and 15's line-start-only `//` comments all checked out, as did the LL(2)
keyword rules; spot-checked `--tree` blocks in GRAMMAR.md matched live output, and the
25 required cases assert real token streams, tree shapes, exact answers and error
positions rather than weakened categories. Three defects did not check out, each fixed
with a regression test (commit a2e492c): the binder's fall-through assert on
two-literal comparisons became a positioned RAError raised *after* the type check (so
`1<'a'` keeps its truthful Type error); file queries now run through bind+execute and
print before any command-line query, skipped under `--tree`, with errors rendered
against the file source; and the binder now sets `strategy="hash"` whenever
`_equi_keys` finds cross-side equality conjuncts, while the runner pins the strategy
per question so Q1-Q5 still measure the fused loop. The differential tests now force
both sides and compare output exactly, and README's strategy section was reconciled
with the new default (plus its stale hardcoded test count replaced with a count-free
phrasing). Four checks green after every edit: 144 tests, ruff, ruff format, mypy.
**What broke:** The three defects the audit read. (D1) `select[1=1](R)` parses per
GRAMMAR 1.5, but the binder fell through to `AssertionError("rejected by the parser")`
and the CLI printed an internal error - the fuzzer's answer-or-RAError property was
false for it, and `select[1=1](R)` is a single character mutation of its own seed
`select[a=1](R)`, so the fixed corpus was one lucky draw away from failing. Proved by
running the fuzzer's exact pipeline on the input, which printed `ESCAPES fuzzer
property: AssertionError`. (D2) `catalog.queries` was write-only: a `;` query in a
--db file parsed and silently did nothing, although README showed exactly that file as
the example. (D3) plan Q6 said "use a hash join" but only the benchmark could select
one; worse, flipping the default would have silently broken the experiment (Q1's
`comparisons == n*n` assert) until the runner pinned both directions. Mid-pass check
failures were also fixed at cause, not suppressed: a misplaced `@parametrize` decorator
broke collection, mypy needed an `isinstance` narrowing around `dataclasses.replace`
on the `BoundNode` union, one test file needed `ruff format`.
**AI was wrong (if any):** An earlier session wrote the D1 assert whose message claims
the parser rejects two-literal comparisons - GRAMMAR.md's operand rule accepts them
(notes/AI_WRONG.md, "assert claimed the parser rejects two-literal comparisons"). And
the hash join docstring claimed its output order differs from the nested loop's;
probing all nine differential shapes showed the orders are identical, so the
multiset-only comparison that protected that claim was upgraded to exact list equality.
**Next:** Push and open the PR; the oral check and the video remain (human-only).
