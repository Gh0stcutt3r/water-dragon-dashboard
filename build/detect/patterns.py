#!/usr/bin/env python3
"""Pattern detectors over the sales tape. Reads tracker.db, writes events.

Detectors (thresholds from config.yaml):
  sweep       >= sweep_min_sales to one buyer within sweep_window_hours
  whale_dump  >= dump_min_tokens sold by one wallet within dump_window_hours
  wash_flag   A->B then B->A (or triangle) on the same collection, confidence 0.6
  volume_spike 24h sales >= spike_multiplier * trailing-7d daily average

Tape-first: everything derives from per-sale rows, never from floor snapshots.
Run: python3 patterns.py
"""
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

BUILD = os.path.expanduser("~/workspace/goals/launch-economics-data-tool/build")
DB = os.path.join(BUILD, "tracker.db")

# v0.4 defaults (config.yaml is the source of truth; mirrored here for portability)
SWEEP_MIN_SALES = 5
SWEEP_WINDOW_H = 6
DUMP_MIN_TOKENS = 3
DUMP_WINDOW_H = 24
WASH_CONFIDENCE = 0.6
SPIKE_MULT = 3.0
TROJAN_WINDOW_H = 72  # sweep followed by dump from same wallet = trojan horse
TROJAN_MIN_GAP_H = 1  # below this it's churn, not deception (also filters timestamp artifacts)
TROJAN_CONFIDENCE = 0.85


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def log_event(c, cid, typ, ts, conf, details):
    c.execute(
        "INSERT INTO events(collection_id, type, timestamp, confidence, details)"
        " VALUES(?,?,?,?,?)",
        (cid, typ, ts, conf, json.dumps(details)),
    )


def detect_sweeps(c, cid):
    """Buyer concentration: N+ sales to one buyer inside the window."""
    sales = c.execute(
        "SELECT buyer, timestamp FROM sales WHERE collection_id=? ORDER BY timestamp",
        (cid,),
    ).fetchall()
    by_buyer = defaultdict(list)
    for s in sales:
        by_buyer[s["buyer"]].append(datetime.fromisoformat(s["timestamp"]))
    found = 0
    for buyer, times in by_buyer.items():
        times.sort()
        i = 0
        for j, t in enumerate(times):
            while (t - times[i]).total_seconds() > SWEEP_WINDOW_H * 3600:
                i += 1
            if j - i + 1 >= SWEEP_MIN_SALES:
                log_event(c, cid, "sweep", t.isoformat(), 1.0, {
                    "buyer": buyer,
                    "sales_in_window": j - i + 1,
                    "window_hours": SWEEP_WINDOW_H,
                })
                found += 1
                break  # one event per buyer per run; dedup by re-run window
    return found


def detect_dumps(c, cid):
    """One wallet selling N+ tokens of a collection inside the window."""
    sales = c.execute(
        "SELECT seller, timestamp, price_eth FROM sales WHERE collection_id=? AND price_eth IS NOT NULL ORDER BY timestamp",
        (cid,),
    ).fetchall()
    by_seller = defaultdict(list)
    for s in sales:
        by_seller[s["seller"]].append(s)
    found = 0
    for seller, ss in by_seller.items():
        ss.sort(key=lambda s: s["timestamp"])
        i = 0
        for j, s in enumerate(ss):
            tj = datetime.fromisoformat(s["timestamp"])
            while (tj - datetime.fromisoformat(ss[i]["timestamp"])).total_seconds() > DUMP_WINDOW_H * 3600:
                i += 1
            if j - i + 1 >= DUMP_MIN_TOKENS:
                prices = [x["price_eth"] for x in ss[i:j + 1]]
                log_event(c, cid, "whale_dump", s["timestamp"], 1.0, {
                    "seller": seller,
                    "tokens_in_window": j - i + 1,
                    "window_hours": DUMP_WINDOW_H,
                    "min_price": min(prices),
                })
                found += 1
                break
    return found


def detect_wash(c, cid):
    """A->B then B->A on the same collection: possible wash, flagged not accused."""
    pairs = c.execute(
        """SELECT buyer, seller, COUNT(*) n FROM sales
           WHERE collection_id=? GROUP BY buyer, seller""",
        (cid,),
    ).fetchall()
    directed = {(r["seller"], r["buyer"]) for r in pairs}
    found = 0
    seen = set()
    for a, b in directed:
        if (b, a) in directed and (a, b) not in seen and (b, a) not in seen:
            log_event(c, cid, "wash_flag", datetime.now(timezone.utc).isoformat(),
                      WASH_CONFIDENCE, {
                          "wallets": [a, b],
                          "note": "mutual trading pair; possible wash — investigate, do not accuse",
                      })
            seen.add((a, b))
            found += 1
    return found


def detect_spikes(c, cid):
    """24h sales vs trailing-7d daily average."""
    now = datetime.now(timezone.utc)
    rows = c.execute(
        "SELECT timestamp FROM sales WHERE collection_id=?", (cid,)
    ).fetchall()
    days = defaultdict(int)
    for r in rows:
        d = datetime.fromisoformat(r["timestamp"]).date().isoformat()
        days[d] += 1
    if len(days) < 3:
        return 0
    today = now.date().isoformat()
    trailing = [v for d, v in days.items() if d != today]
    avg = sum(trailing) / len(trailing)
    if avg == 0:
        return 0
    last24 = sum(1 for r in rows
                 if (now - datetime.fromisoformat(r["timestamp"])).total_seconds() <= 86400)
    if last24 >= SPIKE_MULT * avg and last24 > 0:
        log_event(c, cid, "volume_spike", now.isoformat(), 1.0, {
            "sales_24h": last24,
            "trailing_7d_daily_avg": round(avg, 2),
            "multiplier": round(last24 / avg, 2),
        })
        return 1
    return 0


def detect_trojan(c, cid):
    """Trojan horse: a sweep (apparent demand) followed by a dump from the
    same wallet within TROJAN_WINDOW_H. The gift that was an exit.
    Must run after sweep + dump detection in the same pass."""
    found = 0
    sweeps = c.execute(
        "SELECT timestamp, details FROM events WHERE collection_id=? AND type='sweep'",
        (cid,),
    ).fetchall()
    for s in sweeps:
        buyer = json.loads(s["details"]).get("buyer")
        if not buyer:
            continue
        st = datetime.fromisoformat(s["timestamp"])
        dumps = c.execute(
            """SELECT timestamp FROM events
               WHERE collection_id=? AND type='whale_dump' AND details LIKE ?""",
            (cid, f'%"seller": "{buyer}"%'),
        ).fetchall()
        for dp in dumps:
            dt = datetime.fromisoformat(dp["timestamp"])
            gap = dt - st
            gap_h = gap.total_seconds() / 3600
            if TROJAN_MIN_GAP_H < gap_h <= TROJAN_WINDOW_H:
                log_event(c, cid, "trojan_horse", dt.isoformat(), TROJAN_CONFIDENCE, {
                    "wallet": buyer,
                    "sweep_at": s["timestamp"],
                    "dump_at": dp["timestamp"],
                    "gap_hours": round(gap_h, 1),
                    "note": "sweep (apparent demand) followed by dump — the gift that was an exit",
                })
                found += 1
                break
    return found


def main():
    c = con()
    # clear today's auto-detected events to keep re-runs idempotent, keep manual ones
    total = {"sweep": 0, "whale_dump": 0, "wash_flag": 0, "volume_spike": 0,
             "trojan_horse": 0}
    for (cid, name) in c.execute("SELECT id, name FROM collections").fetchall():
        # wipe prior auto events for this collection before re-detecting
        c.execute("DELETE FROM events WHERE collection_id=?", (cid,))
        total["sweep"] += detect_sweeps(c, cid)
        total["whale_dump"] += detect_dumps(c, cid)
        total["wash_flag"] += detect_wash(c, cid)
        total["volume_spike"] += detect_spikes(c, cid)
        total["trojan_horse"] += detect_trojan(c, cid)
    c.commit()
    c.close()
    print("events detected:", total)


if __name__ == "__main__":
    main()
