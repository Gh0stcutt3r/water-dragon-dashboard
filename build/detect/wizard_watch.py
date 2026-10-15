#!/usr/bin/env python3
"""Quiet volume trigger for the Stacc wizard families.

User-approved 2026-10-13: fold into the morning pull, report ONLY on real
change, stop on request. Backs the 2026-10-11 hold recommendation whose
revisit trigger is "if volume returns."

Reads tracker.db sales tape for the five wizard slugs. Prints
"WIZARD_WATCH: quiet" when nothing meets the bar, otherwise a short report.
State in hidden_files/wizard_watch.json so the same spike isn't re-reported
daily; a new report fires only on a new development after 3+ quiet days.

"Real change" bar (set above the Oct 6-10 dust baseline, where hundreds of
sales totaled fractions of an ETH):
  - trailing-24h family volume > 0.1 ETH, OR
  - any single sale >= 0.02 ETH, OR
  - 24h sales count >= 3x trailing-7d daily average with count >= 20

Covers the sales tape only. It does not read claimable rewards or
fusion/reroll contract events.
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

GOAL = os.path.expanduser("~/workspace/goals/launch-economics-data-tool")
DB = os.path.join(GOAL, "build", "tracker.db")
STATE = os.path.join(GOAL, "hidden_files", "wizard_watch.json")

SLUGS = [
    "staccs-robinhood-homecoming-collection",
    "fireball-wizards",
    "phoenix-wizards",
    "the-lil-wizards",
    "spark-wizards-560723123",
]

VOL_24H_MIN_ETH = 0.1
SINGLE_SALE_MIN_ETH = 0.02
COUNT_SPIKE_MULT = 3.0
COUNT_SPIKE_MIN = 20
REPEAT_QUIET_DAYS = 3


def main():
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    per_slug_24h = {}
    total_24h_vol = 0.0
    total_24h_n = 0
    biggest = None
    for slug in SLUGS:
        rows = con.execute(
            """SELECT s.price_eth, s.timestamp, c.slug FROM sales s
               JOIN collections c ON s.collection_id = c.id
               WHERE c.slug = ? AND s.timestamp >= ?""",
            (slug, day_ago)).fetchall()
        vols = [r["price_eth"] or 0 for r in rows]
        v = sum(vols)
        per_slug_24h[slug] = {"sales": len(rows), "vol_eth": round(v, 4)}
        total_24h_vol += v
        total_24h_n += len(rows)
        for r in rows:
            p = r["price_eth"] or 0
            if biggest is None or p > biggest[0]:
                biggest = (p, slug, r["timestamp"])

    week_n = con.execute(
        """SELECT COUNT(*) FROM sales s JOIN collections c ON s.collection_id = c.id
           WHERE c.slug IN ({}) AND s.timestamp >= ?""".format(
            ",".join("?" * len(SLUGS))),
        (*SLUGS, week_ago)).fetchone()[0]
    con.close()
    daily_avg_7d = week_n / 7.0

    reasons = []
    if total_24h_vol > VOL_24H_MIN_ETH:
        reasons.append(f"24h family volume {total_24h_vol:.4f} ETH > {VOL_24H_MIN_ETH}")
    if biggest and biggest[0] >= SINGLE_SALE_MIN_ETH:
        reasons.append(
            f"single sale {biggest[0]:.4f} ETH on {biggest[1]} at {biggest[2]}")
    if total_24h_n >= COUNT_SPIKE_MIN and daily_avg_7d > 0 and \
            total_24h_n >= COUNT_SPIKE_MULT * daily_avg_7d:
        reasons.append(
            f"24h sales {total_24h_n} >= 3x 7d daily avg ({daily_avg_7d:.1f})")

    try:
        state = json.load(open(STATE))
    except Exception:
        state = {}
    last_report = state.get("last_report_date")

    if not reasons:
        state["last_quiet_date"] = now.strftime("%Y-%m-%d")
        json.dump(state, open(STATE, "w"), indent=1)
        print("WIZARD_WATCH: quiet")
        return

    # Only re-report a new development after enough quiet days.
    if last_report:
        try:
            quiet_days = (now.date() -
                          datetime.strptime(last_report, "%Y-%m-%d").date()).days
        except Exception:
            quiet_days = 99
        if quiet_days < REPEAT_QUIET_DAYS:
            print("WIZARD_WATCH: quiet (already reported, cooling down)")
            return

    state["last_report_date"] = now.strftime("%Y-%m-%d")
    json.dump(state, open(STATE, "w"), indent=1)
    lines = ["WIZARD_WATCH: activity detected"] + \
        [f"  - {r}" for r in reasons] + \
        ["  24h per family: " + ", ".join(
            f"{s.split('-')[0]}:{d['sales']} sales/{d['vol_eth']} ETH"
            for s, d in per_slug_24h.items() if d["sales"])]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
