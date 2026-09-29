# COMP3005 Bonus 1: Relational Algebra Engine

A relational algebra engine built from a hand-written grammar, tokenizer and recursive descent parser.
It is the first component of a larger DBMS.

## Status

Work in progress.
See PLAN.md for the phased plan.

## Requirements

- Python 3.12 or newer (the engine uses the standard library only)
- [uv](https://docs.astral.sh/uv/) for the development tools (pytest, ruff, mypy, matplotlib)

## Setup

```sh
uv sync
```

## Usage

```sh
python ra.py --db examples/employees.ra "project[Name](select[Age>30](Employees))"
python ra.py --tree "project[Name](select[Age>30](Employees))"
```

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

## Design decisions

## Why a self join needs rename

## Known limitations
