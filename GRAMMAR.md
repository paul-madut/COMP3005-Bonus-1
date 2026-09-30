# Grammar

The grammar of the relational algebra language implemented by this engine.
This document is written before the parser, and the parser follows it rule by rule.

## 1. The grammar

### 1.1 Notation

EBNF conventions: `::=` separates a rule name from its right-hand side, `|` separates
alternatives, `{ }` means zero or more repetitions, `[ ]` means one optional occurrence,
and `"..."` are terminal strings. `(* ... *)` marks a comment. Rule names in `lowercase`
are grammar rules, names in `UPPERCASE` are lexical tokens defined in 1.2.

### 1.2 Lexical grammar

```
WORD        ::= letter { letter | digit | "_" }
NUMBER      ::= [ "-" ] digit { digit } [ "." digit { digit } ]
STRING      ::= "'" { any-char-except-quote-or-newline | "''" } "'"
```

- `WORD` covers relation names, attribute names and every keyword - the lexer emits only
  `WORD`, it never decides keyword-ness (see 1.6).
- A `-` is part of a `NUMBER` only when immediately followed by a digit; otherwise `-` is
  a single-character operator token. This rule is what makes case 4 (`Age>-30`) lex as
  `>` `-30` and never a `>-` operator.
- `1x` is a lexical error (a number immediately followed by a letter with no separator),
  not two tokens.
- Inside `STRING`, a doubled quote `''` stands for one literal quote (case 7).
  An unterminated string, or a newline inside a string, is a lexical error reported at
  the position of the opening quote (case 9).
- Whitespace (spaces, tabs, newlines) separates tokens and is otherwise ignored.
- A comment is `//` **only at the start of a line** (after optional horizontal
  whitespace). Elsewhere it is not a comment: in a tuple body `a//b` is swallowed as one
  bare value, and in query mode `/` is an error (`unexpected character '/'`), since no
  query production contains it.

Every token carries its offset, line and column, so every error can point at the source.

#### The tuple-body mode

Inside `{ ... }` of a relation definition the lexer switches to a second mode for
scanning data rows. In this mode a row ends at a newline, and each value is a
`BARE_VALUE` - a run of characters up to `,`, whitespace, `(`, `)`, `'`, `{` or `}`.
A bare value is a number if it scans fully as one, otherwise it is a string.
A quoted value is always a string (`'32'` is a string, `32` is a number).
A `}` ends the mode; the parser never enters tuple-body mode for a query.

### 1.3 Program and relation definitions

```
program      ::= statement { statement }
statement    ::= definition | query
definition   ::= WORD [ "(" attrlist ")" ] "=" "{" { row | newline } "}"
attrlist     ::= WORD { "," WORD }
row          ::= bare-value { "," bare-value } newline
query        ::= expr [ ";" ]
```

A file holds definitions plus optional queries, each query terminated by `;`.
A query given on the command line needs no `;`.

### 1.4 Expressions

```
expr      ::= setterm { ( "union" | "minus" ) setterm }
setterm   ::= product { "intersect" product }
product   ::= primary { "times" primary | "join" "[" cond "]" primary }
primary   ::= unary | "(" expr ")" | WORD
unary     ::= ( "select" | "project" | "rename" ) "[" unary-list "]" primary
unary-list::= cond                                    (* select: one condition *)
             | attrref { "," attrref }                 (* project: attribute list *)
             | rename-spec                             (* rename *)
rename-spec ::= WORD                                  (* rename the relation *)
               | attrref "->" WORD { "," attrref "->" WORD }  (* rename columns *)
attrref   ::= WORD [ "." WORD ]
```

(* Verified against the implemented parser, phase 9. The argument of a unary
operator is a `primary`, not a parenthesized expression: parentheses are only
needed to scope a *binary* expression. So `select[a=1]R union B` parses as
`(select[a=1]R) union B` - the precedence table alone decides it:

  ```
  union
  ├─ select
  │  ├─ a = 1
  │  └─ R
  └─ B
  ```

  while `select[a=1](R union B)` needs the parens to reach inside. The `unary-list`
shape is decided by which operator word was seen, exactly as written above. *)

### 1.5 Conditions

```
cond      ::= andcond { "or" andcond }
andcond   ::= notcond { "and" notcond }
notcond   ::= "not" notcond | catom
catom     ::= "(" cond ")" | operand compop operand
compop    ::= "=" | "!=" | "<" | "<=" | ">" | ">="
operand   ::= WORD [ "." WORD ] | STRING | NUMBER
```

Condition operators: `or` < `and` < `not` < comparison.

### 1.6 Keywords and identifiers

All keywords are lowercase and **contextual**: the lexer never emits a keyword token,
only `WORD`, and the parser decides from position.

- In an operand position, any `WORD` is an attribute reference. So `union` can be an
  attribute name (case 8).
- `select` / `project` / `rename` are operators **only when followed by `[`** - decided
  with two tokens of lookahead (LL(2)).
- `not` is an attribute when followed by a comparison operator; it negates a condition
  only when the next token starts a condition (a `(` or an operand). This is the LL(2)
  decision of `parse_notcond`: `select[not=3](R)` compares an attribute named `not`,
  while `select[not (a=1)](R)` negates. Actual `--tree` output for the first:

  ```
  select
  ├─ not = 3
  └─ R
  ```
- `union`, `minus`, `intersect`, `times`, `join`, `and`, `or` are recognized from
  position: as `WORD`s in operator position they are operators; as attribute references
  (a `WORD` after `(`, `,` or `]` inside a projection list, or a `WORD` operand of a
  comparison) they are plain names.

### 1.7 The language this grammar generates

Every query is a relational expression built from base relation names, the three unary
prefix operators and the four binary operators, with conditions over qualified or
unqualified attributes, quoted strings and exact numbers. The grammar is unambiguous,
left-associative at every binary level, and every construct is decidable with at most
two tokens of lookahead.

## 2. Precedence and associativity

| Level | Operators | Associativity | Enforced by rule |
|---|---|---|---|
| 1 (lowest) | `union`, `minus` | left | `expr` |
| 2 | `intersect` | left | `setterm` |
| 3 | `times`, `join[c]` | left | `product` |
| 4 (highest) | `select`, `project`, `rename`, atoms | prefix | `primary`/`unary` |

So `A union B minus C` = `(A union B) minus C` and `A minus B minus C` =
`(A minus B) minus C`.
Mirrors SQL, where INTERSECT binds tighter than UNION/EXCEPT.

**Confirmed against Relax.**
Relax states its own precedence in a comment in its PEG grammar (`src/db/parser/grammar_ra.pegjs`, lines 826-832, development branch): level 4 `union, difference`, level 3 `intersect`, level 2 the joins and cross product, level 1 the unary operators, level 0 atoms.
Relax counts 4 as the loosest while this table counts 1 as the loosest, so inverting the numbering makes the two orderings identical level for level.
Both points that the required cases turn on agree.
`union` and `difference` share a single level, so case 10's grouping is decided by associativity rather than by precedence.
And Relax's `buildBinary` helper (same file, lines 70-88) folds each repetition into the *left* child of the next operator, so its binary operators are left-associative like these.
Nothing differs beyond notation (`minus` vs `-`/`except`, `times` vs `cross join`) and Relax's larger operator set.
Details and the quoted source are in notes/RELAX_NOTES.md.

Condition operators: `or` (lowest) < `and` < `not` < comparison (highest).

## 3. Ambiguity demonstration

### 3.1 The naive grammar

```
Expr ::= Expr "union" Expr
       | Expr "minus" Expr
       | "(" Expr ")"
       | IDENT
```

### 3.2 Two parse trees for `A union B minus C`

Because the naive `Expr ::= Expr op Expr` accepts both splittings, `A union B minus C`
has two parse trees:

```
      minus                     union
      /    \                    /    \
   union    C                  A    minus
   /   \                         /    \
  A     B                       B      C
```

The left tree groups `(A union B) minus C`; the right one groups
`A union (B minus C)`. The grammar alone cannot choose.
(* Both trees above are hand-drawn: they are what the naive grammar *could*
produce. The implemented parser can only produce the left one - see 3.4. *)

### 3.3 A data instance where the trees disagree

Let `A = {1}`, `B = {2}`, `C = {1}` (attribute `x` everywhere).

- Left tree: `(A union B) minus C = {1,2} - {1} = {2}`.
- Right tree: `A union (B minus C) = {1} ∪ ({2} - {1}) = {1,2}`.

`{2} ≠ {1,2}`, so the parse trees have different meanings and a parser that produced
either silently would compute a different algebra than the one the reader intended.

### 3.4 The stratified grammar and the tree it forces

The stratified grammar of 1.4 has one rule per precedence level and repetitions
`{ ... }` instead of recursion on both sides:

```
expr      ::= setterm { ( "union" | "minus" ) setterm }
```

Because `expr` recurses only through the *right* end of the repetition and the first
`setterm` is parsed before the loop is entered, there is exactly one tree per string.
For `A union B minus C` the loop folds left: `((A union B) minus C)`.
The implemented parser confirms it - `ra.py --tree "A union B minus C"` prints:

```
minus
├─ union
│  ├─ A
│  └─ B
└─ C
```

The right-hand tree of 3.2 is unreachable: there is no production that could
attach `minus C` under `B`.

### 3.5 Associativity of `A minus B minus C` (test case 11)

Left folding inside the loop makes `minus` left-associative:
`A minus B minus C` = `(A minus B) minus C`. `ra.py --tree "A minus B minus C"`
prints exactly that nesting:

```
minus
├─ minus
│  ├─ A
│  └─ B
└─ C
```
With `A = {1,2,3}`, `B = {2}`, `C = {1,2}`: left-associated gives
`{1,2,3} - {2} = {1,3}`, then `{1,3} - {1,2} = {3}`. Right-associated
(`A minus (B minus C) = A minus {} = A`) would give `{1,2,3}` instead.
Set difference is not associative, so the choice is visible in the data.

## 4. Parsing strategy

The parser is recursive descent, one method per grammar rule of section 1, in the same
order: `parse_expr` calls `parse_setterm` which calls `parse_product` which calls
`parse_primary`. A level's `{ ... }` repetition becomes a `while` loop over the operator
tokens of that level (`while peek is "union" or "minus": ...`), and each iteration
folds the result so far with the freshly parsed right operand - this is where the left
associativity of 3.5 comes from.

Left recursion is why the naive grammar is unusable here: `Expr ::= Expr "union" Expr`
makes `parse_expr` call itself on the same input position before consuming a token,
which never terminates. The stratified rules remove left recursion by construction -
the `{ }` repetitions replace the recursive left operand - and no rule in section 1
has a left-recursive production.

Lookahead: the parser needs at most two tokens (1.6): one to see a `WORD`, the second
to see whether a `[` follows (operator) or not (attribute/operand).

A full tree from the implemented parser - every precedence level visible at once
(`ra.py --tree "select[Age>=30](project[Name, Age](Emp)) join[Emp.Dept=Dept.DID] Dept"`):

```
join
├─ Emp.Dept = Dept.DID
├─ select
│  ├─ Age >= 30
│  └─ project
│     ├─ Name
│     ├─ Age
│     └─ Emp
└─ Dept
```

Read bottom-up: `project` binds tightest inside `select`'s argument, the whole
selection is the left input of the join, and the join's condition sits on the edge
where it belongs. The grouping follows the table of section 2 without a single
explicit parenthesis in the source.

## 5. Sources

- Crafting Interpreters, chapters on scanning and parsing (token model, recursive
  descent with one method per rule, precedence climbing by rule layering).
- Wikipedia: EBNF, recursive descent parser, operator-precedence (maximal munch for
  the scanner), left recursion and its removal.
- Dragon Book sections 2.2–2.4 (language definition, syntax, grammars) and 4.4
  (top-down parsing, left-recursion elimination).
- Relax itself: dbis-uibk/relax on GitHub (development branch).
  `src/db/parser/grammar_ra.pegjs` is its relational-algebra PEG grammar, and it is the source for the precedence comparison in section 2: the precedence comment at lines 826-832 and the left-folding `buildBinary` at lines 70-88.
  package.json shows PEG.js as its parser generator, `src/locales/en.json` shows its operator surface and error catalogue, and the README documents its data-group format.
- Notes on Relax, including what the grammar settles and what is still browser-only:
  `notes/RELAX_NOTES.md`.
