"""Plots experiment results on log-log axes for REPORT.md.

Two figures:
- fig_scaling.png: join vs select vs project time against n (Q2, Q3).
- fig_matchrate.png: join time and output size against k at fixed n (Q5).
Report-only: nothing in the engine imports matplotlib.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")  # no display needed
import matplotlib.pyplot as plt


def load(path: str) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def series(rows: list[dict[str, str]], op: str) -> tuple[list[float], list[float]]:
    pts = sorted((float(r["n"]), float(r["time_s"])) for r in rows if r["op"] == op)
    return [p[0] for p in pts], [p[1] for p in pts]


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else "bench/results.csv"
    rows = load(src)

    # --- fig 1: scaling --------------------------------------------------
    fig, ax = plt.subplots(figsize=(6, 4))
    for op, label in (("join", "join (nested loop)"), ("select", "select"), ("project", "project")):
        xs, ys = series(rows, op)
        if xs:
            ax.loglog(xs, ys, "o-", label=label)
    # Q6: the hash join at the largest size, as a single reference point.
    hash_pts = sorted((float(r["n"]), float(r["time_s"])) for r in rows if r["op"] == "hash_join")
    if hash_pts:
        ax.loglog(
            [p[0] for p in hash_pts],
            [p[1] for p in hash_pts],
            "*",
            markersize=14,
            label="join (hash, Q6)",
        )
    ax.set_xlabel("n (tuples per relation)")
    ax.set_ylabel("time (s)")
    ax.set_title("Execution time vs input size")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig("bench/fig_scaling.png", dpi=150)

    # --- fig 2: match-rate sweep ------------------------------------------
    by_k: dict[float, list[float]] = defaultdict(list)
    out_by_k: dict[float, float] = {}
    cmp_by_k: dict[float, float] = {}
    for r in rows:
        if r["op"] == "join_k":
            k = float(r["k"])
            by_k[k].append(float(r["time_s"]))
            out_by_k[k] = float(r["rows_out"])
            cmp_by_k[k] = float(r["comparisons"])
    if by_k:
        # Seconds and counts need separate axes; x is categorical so k=0 can appear.
        ks = sorted(by_k)
        xs = list(range(len(ks)))
        times = [sum(by_k[k]) / len(by_k[k]) for k in ks]

        fig2, ax2 = plt.subplots(figsize=(6.5, 4))
        (l1,) = ax2.plot(xs, times, "o-", color="tab:blue", label="join time (s)")
        ax2.set_xlabel("match rate k")
        ax2.set_ylabel("join time (s)", color="tab:blue")
        ax2.tick_params(axis="y", labelcolor="tab:blue")
        ax2.set_ylim(0, max(times) * 1.35)
        ax2.set_xticks(xs)
        ax2.set_xticklabels([str(int(k)) for k in ks])

        ax3 = ax2.twinx()
        # symlog keeps the k=0 point (0 output tuples) on a mostly-logarithmic axis.
        ax3.set_yscale("symlog", linthresh=1000)
        (l2,) = ax3.plot(
            xs, [out_by_k[k] for k in ks], "s--", color="tab:orange", label="output tuples"
        )
        (l3,) = ax3.plot(
            xs,
            [cmp_by_k[k] for k in ks],
            "^:",
            color="tab:green",
            label="comparisons (constant)",
        )
        ax3.set_ylabel("tuples / comparisons (symlog)")
        ax3.set_ylim(0, max(cmp_by_k.values()) * 10)
        # Explicit ticks: the default symlog locator crowds 0 and 10^2 together.
        ax3.set_yticks([0, 1e4, 1e5, 1e6, 1e7, 1e8])

        n_fixed = int(float(next(r["n"] for r in rows if r["op"] == "join_k")))
        ax2.set_title(f"Match-rate sweep at fixed n ({n_fixed})")
        ax2.grid(True, axis="x", alpha=0.3)
        ax2.legend(handles=[l1, l2, l3], loc="center left", framealpha=0.95)
        fig2.tight_layout()
        fig2.savefig("bench/fig_matchrate.png", dpi=150)

    print("wrote bench/fig_scaling.png" + (", bench/fig_matchrate.png" if by_k else ""))


if __name__ == "__main__":
    main()
