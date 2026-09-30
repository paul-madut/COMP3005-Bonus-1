"""Turns results.csv into the numbers REPORT.md quotes.

- Q1: assert comparisons == n*m exactly, for every join row.
- Q2/Q3: least-squares slope of log(time) against log(n), fitted on the
  larger half of the points (the plan's instruction), for join/select/project.
- Q4: t(1e6) two ways: quadratic extrapolation from the largest size, and
  per-comparison cost times 10^12.
- Q5: the match-rate sweep table.
- Q6: nested vs hash at the largest size.

Usage: python bench/analyze.py [results.csv]
"""

from __future__ import annotations

import csv
import math
import sys


def slope(xs: list[float], ys: list[float]) -> float:
    """Least-squares slope of log y on log x."""
    lx = [math.log(x) for x in xs]
    ly = [math.log(y) for y in ys]
    mx, my = sum(lx) / len(lx), sum(ly) / len(ly)
    num = sum((a - mx) * (b - my) for a, b in zip(lx, ly, strict=True))
    den = sum((a - mx) ** 2 for a in lx)
    return num / den


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "bench/results.csv"
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    joins = sorted((r for r in rows if r["op"] == "join"), key=lambda r: float(r["n"]))
    print(f"== join table ({path}) ==")
    for r in joins:
        n = int(float(r["n"]))
        cmp_ = int(float(r["comparisons"]))
        assert cmp_ == n * n, f"Q1 violated at n={n}: {cmp_} != {n * n}"
        print(
            f"  n={n:>6}  comparisons={cmp_:>12}  time={float(r['time_s']):>10.4f}s"
            f"  out={int(float(r['rows_out'])):>7}  load={float(r['load_s']):.3f}s"
            f"  reps={r['reps']}"
        )
    print("  Q1: comparisons == n*m exactly at every size (asserted).")

    if len(joins) >= 4:
        half = joins[len(joins) // 2 :]
        s_join = slope([float(r["n"]) for r in half], [float(r["time_s"]) for r in half])
        print(f"\n== Q2 ==\n  join slope (larger half, log-log): {s_join:.3f}")

        for op in ("select", "project"):
            pts = sorted((r for r in rows if r["op"] == op), key=lambda r: float(r["n"]))
            if len(pts) >= 4:
                half_op = pts[len(pts) // 2 :]
                s = slope(
                    [float(r["n"]) for r in half_op],
                    [float(r["time_s"]) for r in half_op],
                )
                print(f"  {op} slope (larger half): {s:.3f}")

    print("\n== Q4 ==")
    big = joins[-1]
    n_big, t_big = float(big["n"]), float(big["time_s"])
    factor = (1_000_000 / n_big) ** 2
    quad = t_big * factor
    per_cmp = t_big / float(big["comparisons"])
    print(f"  t({int(n_big)}) = {t_big:.4f}s")
    print(
        f"  quadratic:  t(1e6) = {t_big:.4f} * ({1_000_000 / n_big:.6g})^2"
        f" = {quad / 3600:.2f} h ({quad:.1f}s)"
    )
    print(
        f"  per-comparison cost: {per_cmp * 1e9:.1f} ns"
        f" -> 1e12 comparisons = {per_cmp * 1e12 / 3600:.2f} h"
    )

    k_rows = sorted((r for r in rows if r["op"] == "join_k"), key=lambda r: float(r["k"]))
    if k_rows:
        print("\n== Q5 (match-rate sweep) ==")
        cmps = {int(float(r["comparisons"])) for r in k_rows}
        for r in k_rows:
            print(
                f"  k={int(float(r['k'])):>5}  time={float(r['time_s']):>8.4f}s"
                f"  out={int(float(r['rows_out'])):>8}"
                f"  comparisons={int(float(r['comparisons'])):>10}"
            )
        print(f"  comparisons constant across k: {len(cmps) == 1}")

    hash_rows = [r for r in rows if r["op"] == "hash_join"]
    if hash_rows:
        h = hash_rows[-1]
        n_h = float(h["n"])
        nested = next(r for r in joins if float(r["n"]) == n_h)
        t_n, t_h = float(nested["time_s"]), float(h["time_s"])
        print("\n== Q6 ==")
        print(f"  n = {int(n_h)}")
        print(f"  nested: {t_n:.4f}s, {int(float(nested['comparisons']))} comparisons")
        print(f"  hash:   {t_h:.4f}s, {int(float(h['comparisons']))} comparisons")
        print(
            f"  speedup: {t_n / t_h:.1f}x, comparisons reduced"
            f" {float(nested['comparisons']) / float(h['comparisons']):.0f}x"
        )


if __name__ == "__main__":
    main()
