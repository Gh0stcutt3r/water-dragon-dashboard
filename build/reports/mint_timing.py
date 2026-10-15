#!/usr/bin/env python3
"""Mint-timing read: market regime, day-of-week patterns, cohort status.

Answers "what does the tape say about WHEN" — not a mint-date prediction,
a regime briefing. Run: python3 mint_timing.py
"""
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

BUILD = os.path.expanduser("~/workspace/goals/launch-economics-data-tool/build")
DB = os.path.join(BUILD, "tracker.db")
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    print("=" * 56)
    print("MINT-TIMING READ  ", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print("=" * 56)

    # 1. cohort status
    print("\n--- cohorts ---")
    for cohort, n_coll, n_sales in con.execute(
        """SELECT c.cohort, COUNT(DISTINCT c.id), COUNT(s.id)
           FROM collections c LEFT JOIN sales s ON s.collection_id = c.id
           GROUP BY c.cohort"""
    ):
        print(f"{cohort}: {n_coll} collections, {n_sales} sales")

    # 2. market regime: daily volume, last 14 days
    print("\n--- market regime (broad cohort, all collections) ---")
    daily = defaultdict(lambda: [0, 0.0])
    for r in con.execute("SELECT date(timestamp) d, price_eth FROM sales"):
        daily[r["d"]][0] += 1
        daily[r["d"]][1] += r["price_eth"]
    days = sorted(daily)
    if len(days) >= 14:
        prev, last = days[-14:-7], days[-7:]
    else:
        prev, last = days[: len(days) // 2], days[len(days) // 2 :]
    pv = sum(daily[d][1] for d in prev)
    lv = sum(daily[d][1] for d in last)
    ps = sum(daily[d][0] for d in prev)
    ls = sum(daily[d][0] for d in last)
    print(f"prior 7d:  {ps} sales, {pv:.4f} ETH volume")
    print(f"latest 7d: {ls} sales, {lv:.4f} ETH volume")
    if pv > 0:
        chg = (lv - pv) / pv * 100
        print(f"volume trend: {'UP' if chg > 0 else 'DOWN'} {abs(chg):.1f}%")
    print("daily:")
    for d in days[-14:]:
        n, v = daily[d]
        bar = "#" * min(40, int(v * 4000))
        print(f"  {d}  {n:4d} sales  {v:.4f} ETH  {bar}")

    # 3. day-of-week activity
    print("\n--- day-of-week activity ---")
    dow = defaultdict(int)
    for r in con.execute("SELECT timestamp FROM sales"):
        dow[datetime.fromisoformat(r["timestamp"]).weekday()] += 1
    for i in range(7):
        n = dow[i]
        print(f"  {DOW[i]}: {n:4d} sales  {'#' * min(40, n // 8)}")

    # 4. per-collection price direction (newest vs oldest median)
    print("\n--- price direction (broad cohort) ---")
    for r in con.execute("SELECT id, slug FROM collections"):
        sales = con.execute(
            "SELECT price_eth, timestamp FROM sales WHERE collection_id=? ORDER BY timestamp",
            (r["id"],),
        ).fetchall()
        if len(sales) < 10:
            continue
        q = len(sales) // 4
        old = sorted(s["price_eth"] for s in sales[:q])[q // 2]
        new = sorted(s["price_eth"] for s in sales[-q:])[q // 2]
        arrow = "UP  " if new > old * 1.05 else ("DOWN" if new < old * 0.95 else "FLAT")
        print(f"  {r['slug']}: {arrow}  {old:.5f} -> {new:.5f} ETH  ({len(sales)} sales)")

    # 5. honest limitations
    print("\n--- limitations ---")
    print("mint-comps cohort (free-mint comparables for your launch) has 0 tape so far:")
    print("  city-of-stonks and cartoonals-classics trade off Hood Market and off OpenSea.")
    print("  Their tape must come from their actual venues or Blockscout transfers.")
    print("  Until then, regime/dow reads above are broad-cohort only.")
    print("Hood Market timestamps are approximate (relative '2d ago' labels).")
    con.close()


if __name__ == "__main__":
    main()
