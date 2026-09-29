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
