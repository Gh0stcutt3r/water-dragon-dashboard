#!/usr/bin/env python3
"""Wallet intelligence: dive track records, win rates, dump counts, leaderboards.

Derived purely from the sales tape (buyer/seller per sale). Wallet != person:
one human runs many wallets, some wallets are bots. Track records are signals,
not identities.

Definitions (v0.4):
  dive      buy within DIVE_WINDOW_DAYS of the collection's first observed sale
  dive win  dive where the wallet later sold the same collection above its avg buy
  dump     wallet appears as seller in a whale_dump event

Run: python3 score.py [--top N]
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta

BUILD = os.path.expanduser("~/workspace/goals/launch-economics-data-tool/build")
DB = os.path.join(BUILD, "tracker.db")
DIVE_WINDOW_DAYS = 7


def main():
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--top" else 10
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # collection launch proxy: first observed sale
    launch = {
        r["id"]: datetime.fromisoformat(r["t"])
        for r in con.execute(
            "SELECT collection_id id, MIN(timestamp) t FROM sales GROUP BY collection_id"
        )
    }

    wallets = [r["address"] for r in con.execute("SELECT address FROM wallets")]
    for w in wallets:
        buys = con.execute(
            "SELECT collection_id, price_eth, timestamp FROM sales WHERE buyer=? AND price_eth IS NOT NULL", (w,)
        ).fetchall()
        sells = con.execute(
            "SELECT collection_id, price_eth, timestamp FROM sales WHERE seller=? AND price_eth IS NOT NULL", (w,)
        ).fetchall()

        # group buys by collection
        by_coll = {}
        for b in buys:
            by_coll.setdefault(b["collection_id"], []).append(b)
        sell_avg = {}
        for s in sells:
            sell_avg.setdefault(s["collection_id"], []).append(s["price_eth"])

        dives = dive_wins = 0
        for cid, bb in by_coll.items():
            first = launch.get(cid)
            if not first:
                continue
            early = [b for b in bb
                     if (datetime.fromisoformat(b["timestamp"]) - first)
                     <= timedelta(days=DIVE_WINDOW_DAYS)]
            if not early:
                continue
            dives += 1
            avg_buy = sum(b["price_eth"] for b in early) / len(early)
            # did they later sell this collection above avg buy?
            later = [p for p in sell_avg.get(cid, []) if p > avg_buy]
            if later:
                dive_wins += 1

        buy_total = sum(b["price_eth"] for b in buys)
        sell_total = sum(s["price_eth"] for s in sells)
        dumps = con.execute(
            "SELECT COUNT(*) FROM events WHERE type='whale_dump' AND details LIKE ?",
            (f'%"seller": "{w}"%',),
        ).fetchone()[0]
        win_rate = round(dive_wins / dives, 3) if dives else None

        con.execute(
            """INSERT INTO wallet_scores(wallet, dives, dive_wins, win_rate,
                                         realized_pnl_eth, dumps, updated_at)
               VALUES(?,?,?,?,?,?,datetime('now'))
               ON CONFLICT(wallet) DO UPDATE SET
                 dives=excluded.dives, dive_wins=excluded.dive_wins,
                 win_rate=excluded.win_rate, realized_pnl_eth=excluded.realized_pnl_eth,
                 dumps=excluded.dumps, updated_at=datetime('now')""",
            (w, dives, dive_wins, win_rate, round(sell_total - buy_total, 6), dumps),
        )
    con.commit()

    print(f"=== top {top_n} dive wallets (min 2 dives) ===")
    for r in con.execute(
        """SELECT wallet, dives, dive_wins, win_rate, realized_pnl_eth, dumps
           FROM wallet_scores WHERE dives >= 2
           ORDER BY win_rate DESC, dives DESC LIMIT ?""",
        (top_n,),
    ):
        print(f"{r['wallet'][:10]}…{r['wallet'][-4:]}  dives={r['dives']} "
              f"wins={r['dive_wins']} wr={r['win_rate']} pnl={r['realized_pnl_eth']} ETH "
              f"dumps={r['dumps']}")
    print("=== most active dumpers ===")
    for r in con.execute(
        "SELECT wallet, dumps FROM wallet_scores WHERE dumps > 0 ORDER BY dumps DESC LIMIT 5"
    ):
        print(f"{r['wallet'][:10]}…{r['wallet'][-4:]}  dumps={r['dumps']}")
    con.close()


if __name__ == "__main__":
    main()
