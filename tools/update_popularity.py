#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compute `foods.popularity_score` from real signals.

Task 9 of `ML_PIPELINE.md` section 12. The column currently reads 0 for **all
318 foods** because it only ever had `DEFAULT 0` and nobody computed it, and
the consequence is worse than it looks: section 10.1 makes `popularity` the
baseline that **must** be beaten, so if it is equal across every food it
ranks nothing — every food ties, and the core research question becomes a
comparison against noise.

The formula, the definitions of "seen / liked", and the reasoning behind the
Wilson lower bound all live in `ml/popularity.py`. This file is only the
command-line wrapper.

One important note: the score written here is computed from **every** signal,
so it is right for **serving** but must not be used when **evaluating** —
`ml/evaluate.py` rebuilds popularity from the training folds alone. See the
header of `ml/popularity.py`.

Run:
    python tools/update_popularity.py            # dry run, writes nothing
    python tools/update_popularity.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import connect, use_utf8  # noqa: E402
from ml.popularity import from_database  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None)
    parser.add_argument("--apply", action="store_true", help="write to foods")
    t = parser.parse_args(argv)

    cn = connect(t.db)
    try:
        rows = from_database(cn)
        with_signal = sum(1 for d in rows if int(d["n_seen"]) > 0)
        changed = sum(
            1 for d in rows if abs(d["score"] - float(d["previous"])) > 1e-9
        )

        print(f"{len(rows)} foods - {with_signal} with a signal")
        if with_signal == 0:
            print(
                "\nNo user signals yet — every food stays at 0.\n"
                "This is NOT an error: `popularity_score` is derived from\n"
                "behaviour, so it only means anything once real data has been\n"
                "collected (ML_PIPELINE.md section 11.3). Until then the\n"
                "`popularity` baseline stays degenerate and `ml/evaluate.py`\n"
                "will keep reporting that the comparison carries no weight."
            )
            return 0

        ranked = sorted(
            (
                (d["score"], int(d["n_liked"]), int(d["n_seen"]), d["name"])
                for d in rows
                if int(d["n_seen"]) > 0
            ),
            reverse=True,
        )
        print(f"\n{'score':>7}  {'liked/seen':>11}  food")
        for score, n_liked, n_seen, name in ranked[:10]:
            print(f"{score:>7.4f}  {n_liked:>5}/{n_seen:<5}  {name}")
        if len(ranked) > 10:
            print(f"   ... and {len(ranked) - 10} more")

        print(f"\n{changed} foods changed score.")
        if not t.apply:
            print("Dry run — nothing written. Add --apply to write to foods.")
            return 0

        with cn.cursor() as cur:
            cur.executemany(
                "UPDATE foods SET popularity_score = %s WHERE id = %s",
                [(d["score"], d["id"]) for d in rows],
            )
        cn.commit()
        print(f"Updated popularity_score for {len(rows)} foods.")
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
