"""Data generator: writes R(a, b) and S(b, c) with controlled sizes and match rate.

Design (plan Phase 7):
- `a` and `c` are unique ids, so no tuples collapse under set semantics --
  otherwise the real n silently shrinks and the Q1 formula breaks.
- The `b` domain has size m/k, so each R tuple matches about k tuples of S
  and the join output is about n*k rows.
"""

from __future__ import annotations

import argparse
import random


def generate(
    n: int, m: int, match_rate: int, seed: int
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Return (R, S) as row lists: R(a,b) n rows, S(b,c) m rows."""
    rng = random.Random(seed)
    if match_rate > 0:
        b_domain = max(m // match_rate, 1)
        r = [(i + 1, rng.randrange(b_domain)) for i in range(n)]
        s = [(rng.randrange(b_domain), i + 1) for i in range(m)]
    else:
        # k=0: disjoint b ranges, so the join still compares all n*m pairs but
        # emits nothing.  This is the Q5 baseline for output-construction cost.
        b_domain = max(m, 1)
        r = [(i + 1, rng.randrange(b_domain)) for i in range(n)]
        s = [(b_domain + rng.randrange(b_domain), i + 1) for i in range(m)]
    return r, s


def render(name: str, attrs: tuple[str, ...], rows: list[tuple[int, int]]) -> str:
    body = "\n".join("  " + ", ".join(str(v) for v in row) for row in rows)
    return f"{name} ({', '.join(attrs)}) = {{\n{body}\n}}"


def main() -> None:
    ap = argparse.ArgumentParser(description="generate bench data R(a,b), S(b,c)")
    ap.add_argument("--n", type=int, default=1000, help="rows of R")
    ap.add_argument("--m", type=int, default=1000, help="rows of S")
    ap.add_argument("--match-rate", type=int, default=1, help="S-matches per R row")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="-", help="output file, '-' for stdout")
    args = ap.parse_args()

    r, s = generate(args.n, args.m, args.match_rate, args.seed)
    header = f"// n={args.n} m={args.m} match-rate={args.match_rate} seed={args.seed}\n"
    text = header + render("R", ("a", "b"), r) + "\n\n" + render("S", ("b", "c"), s) + "\n"
    if args.out == "-":
        print(text, end="")
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.out}: R={args.n} rows, S={args.m} rows")


if __name__ == "__main__":
    main()
