"""Runs the join, select and project experiments at each size and writes CSV.

Questions (plan Phase 8):
- Q1: nested-loop join comparisons are exactly n*m (asserted per row).
- Q2: time vs n on log-log -> slope ~2 for the join.
- Q3: select and project slopes ~1.
- Q4: extrapolate t(1e6) two ways and compare.
- Q5: sweep the match rate k at fixed n: comparisons constant, time grows
  with output construction.
- Q6: hash join vs nested loop on the same data.

Timing methodology: perf_counter_ns around execution only (load time is
reported separately), median of 3 runs for small n, single run for the
largest, GC disabled during the timed region.
"""

from __future__ import annotations

import argparse
import csv
import gc
import sys
import time
from dataclasses import replace as dataclasses_replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gen import generate  # noqa: E402  # gen.py lives next to this script

from relalg.binder import (  # noqa: E402
    Binder,
    BoundIntersect,
    BoundJoin,
    BoundMinus,
    BoundNode,
    BoundProject,
    BoundRename,
    BoundSelect,
    BoundTimes,
    BoundUnion,
)
from relalg.catalog import Catalog  # noqa: E402
from relalg.executor import execute  # noqa: E402
from relalg.parser import parse  # noqa: E402


def build_catalog(n: int, m: int, k: int, seed: int) -> Catalog:
    r, s = generate(n, m, k, seed)
    c = Catalog()
    c.load(
        "R (a, b) = {\n"
        + "\n".join(f"  {a}, {b}" for a, b in r)
        + "\n}\n"
        + "S (b, c) = {\n"
        + "\n".join(f"  {b}, {c}" for b, c in s)
        + "\n}"
    )
    return c


def timed_run(catalog: Catalog, query: str, hash_join: bool = False) -> tuple[float, int, int]:
    """Execute once; return (seconds, rows_out, comparisons)."""
    plan = Binder(catalog).bind(parse(query))
    if hash_join:
        # Walk the plan and flip every join to the hash strategy (Q6).
        plan = _switch_to_hash(plan)
    assert plan is not None
    gc_was_on = gc.isenabled()
    gc.disable()
    t0 = time.perf_counter_ns()
    _, rows, stats = execute(plan)
    n_out = len(list(rows))
    elapsed = time.perf_counter_ns() - t0
    if gc_was_on:
        gc.enable()

    def count_comparisons(st: object) -> int:
        total = getattr(st, "comparisons", 0)
        return total + sum(count_comparisons(ch) for ch in getattr(st, "children", []))

    return elapsed / 1e9, n_out, count_comparisons(stats)


def _switch_to_hash(node: BoundNode) -> BoundNode:
    """Rebuild the plan bottom-up, switching every equi-join to hash (Q6)."""
    if isinstance(node, BoundJoin) and node.equi_keys:
        node = dataclasses_replace(node, strategy="hash")
    if isinstance(node, (BoundSelect, BoundProject, BoundRename)):
        return dataclasses_replace(node, input=_switch_to_hash(node.input))
    if isinstance(node, (BoundUnion, BoundMinus, BoundIntersect, BoundTimes, BoundJoin)):
        return dataclasses_replace(
            node,
            left=_switch_to_hash(node.left),
            right=_switch_to_hash(node.right),
        )
    return node


def main() -> None:
    ap = argparse.ArgumentParser(description="run the phase-8 experiments")
    ap.add_argument("--sizes", default="1000,2000,4000,8000,16000,32000,64000")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="bench/results.csv")
    ap.add_argument("--quick", action="store_true", help="cap the sizes at 8000 for a fast pass")
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes.split(",")]
    if args.quick:
        sizes = [n for n in sizes if n <= 8000]
    out_rows: list[dict[str, object]] = []
    join_by_n: dict[int, tuple[float, int, int]] = {}

    for n in sizes:
        k = 1  # the plan fixes k=1 for the size sweep
        catalog = build_catalog(n, n, k, args.seed)
        load_s = _load_time(n, args.seed)

        reps = 3 if n <= 8000 else 1

        join_s, join_out, join_cmp = median_of(catalog, "R join[R.b=S.b] S", reps)
        assert join_cmp == n * n, f"Q1 violated at n={n}: {join_cmp} != {n * n}"
        join_by_n[n] = (join_s, join_out, join_cmp)
        sel_s, sel_out, _ = median_of(catalog, "select[b>=0](R)", reps)
        proj_s, proj_out, _ = median_of(catalog, "project[b](R)", reps)

        out_rows.append(
            dict(
                n=n,
                k=k,
                op="join",
                time_s=join_s,
                rows_out=join_out,
                comparisons=join_cmp,
                load_s=load_s,
                reps=reps,
            )
        )
        out_rows.append(
            dict(
                n=n,
                k=k,
                op="select",
                time_s=sel_s,
                rows_out=sel_out,
                comparisons=sel_out,
                load_s=load_s,
                reps=reps,
            )
        )
        out_rows.append(
            dict(
                n=n,
                k=k,
                op="project",
                time_s=proj_s,
                rows_out=proj_out,
                comparisons=0,
                load_s=load_s,
                reps=reps,
            )
        )
        print(
            f"n={n:>6}  join {join_s:8.4f}s  select {sel_s:8.4f}s  "
            f"project {proj_s:8.4f}s  (out={join_out})"
        )

    # Q5: match-rate sweep at fixed n.
    n_fixed = min(8000, max(sizes))
    for k in (0, 1, 10, 100, 1000):
        catalog = build_catalog(n_fixed, n_fixed, k, args.seed)
        s0, out0, cmp0 = timed_run(catalog, "R join[R.b=S.b] S")
        out_rows.append(
            dict(
                n=n_fixed,
                k=k,
                op="join_k",
                time_s=s0,
                rows_out=out0,
                comparisons=cmp0,
                load_s=0.0,
                reps=1,
            )
        )
        print(f"k={k:>5}  join {s0:8.4f}s  out={out0}  comparisons={cmp0}")

    # Q6: hash vs nested at the largest size.  The nested numbers come from the
    # size sweep above -- same seed means the same data, so re-running it would
    # only re-measure the identical query.
    n_big = max(sizes)
    nested_s, nested_out, nested_cmp = join_by_n[n_big]
    catalog = build_catalog(n_big, n_big, 1, args.seed)
    hash_s, hash_out, hash_cmp = timed_run(catalog, "R join[R.b=S.b] S", hash_join=True)
    assert hash_out == nested_out, (
        f"Q6 strategies disagree: hash emitted {hash_out}, nested {nested_out}"
    )
    out_rows.append(
        dict(
            n=n_big,
            k=1,
            op="hash_join",
            time_s=hash_s,
            rows_out=hash_out,
            comparisons=hash_cmp,
            load_s=0.0,
            reps=1,
        )
    )
    print(
        f"Q6 @ n={n_big}: nested {nested_s:.4f}s ({nested_cmp} comparisons), "
        f"hash {hash_s:.4f}s ({hash_cmp} comparisons, out={hash_out})"
    )

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"wrote {path}")


def median_of(catalog: Catalog, query: str, reps: int) -> tuple[float, int, int]:
    """Run `query` reps times and return the median (seconds, rows, comparisons)."""
    results = [timed_run(catalog, query) for _ in range(reps)]
    results.sort(key=lambda r: r[0])
    return results[len(results) // 2]


def _load_time(n: int, seed: int) -> float:
    t0 = time.perf_counter_ns()
    build_catalog(n, n, 1, seed)
    return (time.perf_counter_ns() - t0) / 1e9


if __name__ == "__main__":
    main()
