# AI was wrong: scratch list

Log every time AI assistance gave something wrong, slow or incomplete, as soon as it happens.
DESIGN_LOG.md needs at least three of these, written up in two or three sentences each.
Details fade fast, so capture the exact prompt, output and evidence while it is fresh.

## Template

```
### YYYY-MM-DD - short title
- Phase / file:
- What I asked:
- What it gave me:
- Why it was wrong / slow / incomplete:
- How I found out (failing test case #, measurement, reading, Relax, etc.):
- What I did instead:
- Copied into DESIGN_LOG.md: yes / no
```

## Entries

### 2026-09-29 - hallucinated Relax source layout
- Phase / file: Phase 1, notes/RELAX_NOTES.md
- What I asked: verify Relax's operator precedence against its source before drafting GRAMMAR.md.
- What it gave me: (working assumption from the plan) that the relax repo has a
  doc/lang/en/relax-guide.md and a parser directory under src/calc2/parser with the PEG grammar.
- Why it was wrong / slow / incomplete: neither path exists (404 on raw fetch and on the
  contents API). The parser is loaded via pegjs-loader from somewhere in the webpack
  graph and the help text is generated into a 119 KB help.tsx, not a markdown doc.
- How I found out: fetched doc/lang/en/relax-guide.md, src/calc2/parser and
  src/calc2/parser?ref=development - all 404; listed the real trees with the GitHub API.
- What I did instead: used what is verifiable (package.json: pegjs; src/locales/en.json:
  the full operator toolbar and error-message catalogue) and wrote the precedence
  questions as a 12-step browser checklist in RELAX_NOTES.md instead of trusting
  invented answers.
- Follow-up 2026-09-30: the grammar *does* exist as a file, at
  `src/db/parser/grammar_ra.pegjs` - the guess was wrong about the directory
  (`src/calc2/parser/`), not about the file existing. Found it by listing the repo tree
  with the GitHub API and grepping the paths for "peg", instead of guessing a path and
  fetching it. It states Relax's precedence in a comment and folds binary operators
  left, which settles checklist questions 1-3 from source rather than from the browser
  (notes/RELAX_NOTES.md, "Precedence, settled from the grammar"). Lesson: when a fetch
  404s, enumerate the tree before concluding the thing is not there.
- Copied into DESIGN_LOG.md: yes

### 2026-09-29 - file writes came back as placeholder junk
- Phase / file: Phase 3, tests/test_lexer.py (also an early relalg/binder.py edit)
- What I asked: "write the Phase 3/4 test file, cases 1–9, direct token-stream tests".
- What it gave me: a file whose body was template placeholder text instead of the
  requested tests - the right header, then stubs where the assertions should have been.
  A later binder edit did the same thing mid-file.
- Why it was wrong / slow / incomplete: nothing runnable, and it looked superficially
  plausible, so it would have been committed as "the test suite".
- How I found out: read the file back before running it (and ruff/mypy flagged the
  binder edit immediately after).
- What I did instead: rewrote both files in full and re-read every file the moment a
  write returns anything unexpected; a write_file that reports success is not evidence
  the content is right.
- Copied into DESIGN_LOG.md: yes

### 2026-09-29 - hash join keyed on the wrong coordinates
- Phase / file: Phase 7, relalg/operators.py `_pull_hash_join` (Q6)
- What I asked: implement the hash join for the benchmark: build on S's keys, probe with R.
- What it gave me: a hash table keyed by indexing the *right* row with positions computed
  against the *concatenated* (left ++ right) row, so buckets were wrong whenever the left
  arity was non-zero - silently wrong join output, not an exception.
- Why it was wrong / slow / incomplete: off-by-relation index arithmetic; the results
  were plausible-looking rows from the wrong buckets, so only a comparison against the
  nested loop would reveal it.
- How I found out: a probe script that ran the same query with both strategies and diffed
  the outputs. No test covered the hash path at that point - the Q6 code was added after
  the semantics suite was written.
- What I did instead: rebased the right-side indexes by the left arity (`j - l_arity`)
  and added the mixed equi/theta case to the probe. Lesson recorded: a second strategy
  for an existing operator needs its own equivalence test against the first.
- Copied into DESIGN_LOG.md: yes

### 2026-10-05 - assert claimed the parser rejects two-literal comparisons
- Phase / file: Phase 5 binder work, relalg/binder.py `_comparison` (found as defect D1
  of the pre-PR correctness audit)
- What I asked: implement the comparison predicate for the binder (static type checking
  of both operands before execution).
- What it gave me: a fall-through `raise AssertionError("comparison with two literals is
  rejected by the parser")` when both operands are literals - a claim about the parser
  that was never true: GRAMMAR.md 1.5 has `catom ::= "(" cond ")" | operand compop
  operand` with `operand ::= WORD ["." WORD] | STRING | NUMBER`, so `select[1=1](R)`
  parses fine.
- Why it was wrong / slow / incomplete: a grammatical query died as an internal error
  instead of one of the five categories, and the fuzzer's answer-or-RAError property
  was false for it - `select[1=1](R)` is one `char` mutation (a -> 1) of the seed
  `select[a=1](R)` in the fuzzer's own corpus, so the fixed seed and iteration count
  were the only reason the suite stayed green.
- How I found out: the audit read the binder's final `raise` next to the GRAMMAR.md
  operand rule, then ran the fuzzer's exact pipeline on `select[1=1](R)` and got
  `ESCAPES fuzzer property: AssertionError` (the CLI separately printed
  `internal error: AssertionError`, exit 1).
- What I did instead: raise a positioned `RAError` ("comparison of two literals (...):
  at least one side must be an attribute") *after* the compatibility check so
  `1<'a'` keeps its Type error; added `test_two_literal_comparison_is_answer_or_raerror`
  running the fuzzer's property on that input and put `select[1=1](R)` into the CLI
  no-traceback cases. Lesson: an assert whose message blames another component is a
  claim about that component - check it against that component's spec, and exercise a
  fuzzer property with inputs hand-built to target its known blind spot.
- Copied into DESIGN_LOG.md: yes
