# Relax observations

Notes from experimenting with Relax at https://dbis-uibk.github.io/relax.
Where my engine deliberately differs from Relax, say so here and in GRAMMAR.md.

## Questions to answer

- [x] How does `A ∪ B - C` group? And `A - B - C`?
      Both left, from `grammar_ra.pegjs` - see "Precedence, settled from the grammar".
- [x] Does `∩` bind tighter than `∪` and `-`? Yes (its own level, 3 vs 4).
- [x] Where do `×` and `⨝` sit relative to the set operators? Tighter than both (level 2).
- [ ] What happens on a self join without renaming?
- [ ] How are attributes named after a join where both sides have the same attribute?
- [ ] Does projection remove duplicates?
- [ ] What does it do with `π Name, Name`?
- [ ] What does comparing a number to a string do?
- [ ] What does union of incompatible schemas report?
- [ ] How does it display an empty result?

## How to run each experiment (45 min checklist)

Paste the group below into a new Relax group, then run each query and record what happens.
One line per result under "Session log".

```
group:precedence-lab
description:lab for GRAMMAR.md precedence claims

A = {x
1
2
3
}

B = {x
2
}

C = {x
1
2
}

R = {a, b
1, 10
2, 20
}

S = {b, c
10, 'x'
30, 'y'
}
```

1. Precedence of `-` vs `∪`: run `A ∪ B - C` and `(A ∪ B) - C` and `A ∪ (B - C)`.
   Note which of the parenthesized forms the bare form reproduces. (B - C = {2}, so the
   two parenthesized forms disagree: {2} vs {1,2,3}.)
2. Associativity of `-`: run `A - B - C` and `(A - B) - C` and `A - (B - C)`
   (gives {3} vs {1,2,3}).
3. Intersect level: run `A ∪ B ∩ C` with a B where `B ∩ C ≠ B`, so the two groupings differ.
4. Join vs set operators: run `R ⨝ S ∪ R` and `(R ⨝ S) ∪ R` - if they differ, the join
   binds tighter than union; if Relax rejects the bare form, that is the answer instead.
5. Self join without renaming: `R ⨝[R.a >= R.a] R` - expect an ambiguity error on `R.a`
   (Relax reports "column is ambiguous"), or a rejected duplicate-column join
   ("join would result in non unique column names" per its message catalogue).
6. Qualified names after join: `R ⨝[R.b = S.b] S` then try `σ R.b > 5 (...)` - does the
   result keep both qualifiers or merge `b` into one column?
7. Duplicate elimination: `π b R` on data with repeated `b` - count the rows.
   Relax has a separate `∂` (delta) operator for duplicate elimination, which strongly
   suggests projection itself does not dedup. Confirm with `π b R` vs `∂ (π b R)`.
8. `π b, b R`: expect a "non unique attribute" parser error ("non unique attribute {name}
   in column {index}" is in its message catalogue).
9. Number vs string comparison: `σ a = '1' R` - expect "could not compare value if types
   are different" (in the catalogue), i.e. a runtime type error, exactly the case 22 stance.
10. Union with incompatible schemas: `R ∪ S` - expect "schemas are not unifiable:
    types are different or size is different".
11. Empty result: any query matching nothing (e.g. `σ a > 99 R`) - note whether the
    table header still renders and how the empty body looks.
12. Keywords as names: define a relation named `union` if the group editor allows it,
    and try `σ union = 3 R` if there is an attribute called `union`.

## What the source already confirms (no browser needed)

Read from the Relax repo (github.com/dbis-uibk/relax, development branch) on 2026-09-29:

- It parses with **PEG.js** (`pegjs` + `pegjs-loader` in package.json), i.e. an
  ordered-choice PEG, not a recursive-descent parser with explicit precedence levels.
  PEG choice is greedy and ordered, so its precedence comes from how the grammar nests
  the rules - worth one experiment (1-4 above) to see the effective grouping.
- Operator surface (from its toolbar strings and message catalogue): σ (sigma),
  π (pi), ρ (rho, both `ρ x(A)` for relation rename and `ρ y←a(A)` for column rename),
  ∂ (duplicate elimination), τ (order by), γ (group by), ×, ⋈ (natural/θ-join),
  the four outer joins, semi and anti joins, ÷, ∪, ∩, −.
- Set operators are written with explicit parentheses in its own toolbar examples
  (`( A ) ∪ ( B )`), which hints the grouping of chained set operators is something a
  user is expected to spell out - still worth experiment 1-3.
- Error messages confirm the semantics stance my engine takes:
  - comparing different types is an error ("could not compare value if types are
    different: {typeA} != {typeB}") - supports rejecting `Age>'30'` at bind time;
  - ambiguous columns are an error ("column \"{column}\" is ambiguous in {schema}");
  - union checks schema compatibility ("schemas are not unifiable: types are different
    or size is different");
  - `π b, b`-style duplicates are a parser error ("non unique attribute {name} in
    column {index}").
- Data groups use `A = {a, b ...}` with `name:type` headers (`a:string, b:number`),
  dates as `YYYY-MM-DD`, `null` values, and `--` line comments.
  My engine differs on purpose: types are inferred, not declared, and only `//`
  comments exist (and only at the start of a line).

## Precedence, settled from the grammar (2026-09-30)

The 12-step browser lab was meant to *infer* Relax's precedence from behaviour.
That turned out to be unnecessary: Relax states its precedence in a comment inside its own PEG grammar, and the rule layering below the comment implements it.

Source: `src/db/parser/grammar_ra.pegjs`, development branch, read 2026-09-30 from <https://raw.githubusercontent.com/dbis-uibk/relax/development/src/db/parser/grammar_ra.pegjs>.
This is the file the 2026-09-29 session looked for and failed to find: it guessed `src/calc2/parser/`, and the real path is `src/db/parser/` (see notes/AI_WRONG.md, "hallucinated Relax source layout").

Verbatim from the grammar, lines 826-832:

```
precedence: (low to high)

4: union, difference
3: intersect
2: crossJoin, thetaJoin, naturalJoin, leftOuterJoin, rightOuterJoin, fullOuterJoin, leftSemiJoin, rightSemiJoin, antiJoin, division
1: projection, selection, renameColumns, renameRelation, groupBy, orderBy
0: table, relation, ( ex )
```

Relax numbers levels so that **4 is the loosest**, while PLAN.md decision 2 numbers them so that **1 is the loosest**.
Once the numbering is inverted the two orderings are identical, level for level:

| Relax level | Relax operators | My level (decision 2) | My operators |
|---|---|---|---|
| 4 (loosest) | `union`, `difference` | 1 (loosest) | `union`, `minus` |
| 3 | `intersect` | 2 | `intersect` |
| 2 | `crossJoin`, `thetaJoin`, the outer/semi/anti joins, `division` | 3 | `times`, `join[c]` |
| 1 | `projection`, `selection`, `renameColumns`, `renameRelation`, `groupBy`, `orderBy` | prefix ops | `select[c]`, `project[…]`, `rename[…]` |
| 0 (tightest) | `table`, `relation`, `( ex )` | atoms | relation name, `( expr )` |

Two consequences matter for the assignment's cases:

- **`union` and `difference` share one level** (both at 4), exactly as in decision 2.
  So `A ∪ B - C` is *not* `A ∪ (B - C)`: the two operators compete at the same level, and grouping falls to associativity.
  This is required case 10.
- **The fold is left-associative.**
  Each level is written as `first:<tighter> rest:( op1 / op2 )+ { return buildBinary(first, rest); }`.
  `buildBinary` (grammar_ra.pegjs lines 70-88) seeds `root = rest[0]` with `root.child = first`, then reassigns `n.child = root; root = n` for each later element, folding the accumulated tree in as the *left* child of the next operator.
  So `A - B - C` parses as `(A - B) - C`, which is required case 11.

That is the same shape as my `expr ::= setterm { ("union" | "minus") setterm }` with a left fold inside the loop, so **no change to GRAMMAR.md §2 is needed**: my precedence table already matches Relax.
The difference in *notation* stands (`minus` / `except`, `times` / `cross join`), and so does the smaller operator set.

The mechanism differs even though the result agrees.
Relax gets precedence from one PEG rule per level with ordered choice, while my parser gets it from one recursive-descent function per level.
The rule layering is the part that carries the precedence in both, which is why the two agree.

### Still browser-only

Questions 4-12 are about *runtime* behaviour (error text, output rendering, dedup) rather than grammar, so the grammar file cannot settle them.
The message catalogue in `src/locales/en.json` already supports the stances my engine takes on 5, 8, 9 and 10 (see the previous section).
Questions 6, 7, 11 and 12 remain genuinely open, and none of them is load bearing for any claim in GRAMMAR.md or the README.

## Deliberate differences from Relax

- No `∂`: my projection keeps the set semantics of the algebra (dedup always) - the
  assignment's case 23 expects exactly two tuples for `π DID`.
- One join operator: θ-join with a condition; no outer/semi/anti joins, no γ, no τ.
- Types inferred per column, `unknown` for empty relations; no declared types, no dates.
- Textual syntax (`select[c](R)`), not the Greek-letter surface syntax.

## Session log

(Fill during the browser session: one line per experiment, result + surprise.)
