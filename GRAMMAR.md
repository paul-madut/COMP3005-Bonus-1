# Grammar

The grammar of the relational algebra language implemented by this engine.
This document is written before the parser, and the parser follows it rule by rule.

## 1. The grammar

### 1.1 Notation

<!-- EBNF conventions used: ::=, |, { } for zero or more, [ ] for optional, "..." for terminals. -->

### 1.2 Lexical grammar

<!-- WORD, NUMBER, STRING, BARE_VALUE, punctuation, comparison operators, comments, whitespace. -->
<!-- Maximal munch rule, the '' escape, and the tuple-body lexer mode. -->

### 1.3 Program and relation definitions

### 1.4 Expressions

### 1.5 Conditions

### 1.6 Keywords and identifiers

<!-- Contextual keyword rule (test case 8), with the exact lookahead used at each decision point. -->

### 1.7 The language this grammar generates

## 2. Precedence and associativity

| Level | Operators | Associativity | Enforced by rule |
|---|---|---|---|
| 1 (lowest) | | | |
| 2 | | | |
| 3 | | | |
| 4 (highest) | | | |

<!-- Condition operators: or < and < not. -->

## 3. Ambiguity demonstration

### 3.1 The naive grammar

```
Expr ::= Expr "union" Expr
       | Expr "minus" Expr
       | "(" Expr ")"
       | IDENT
```

### 3.2 Two parse trees for `A union B minus C`

### 3.3 A data instance where the trees disagree

### 3.4 The stratified grammar and the tree it forces

### 3.5 Associativity of `A minus B minus C` (test case 11)

## 4. Parsing strategy

<!-- Recursive descent: why, what left recursion does to it, and the exact rules where it was removed. -->

## 5. Sources

<!-- What I read, and where AI assistance was wrong. -->
