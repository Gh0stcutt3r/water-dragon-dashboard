#!/usr/bin/env python3
"""Pull sales tape from Hood Market activity pages into tracker.db.

Keyless source (no API key needed). Run: python3 pull_tape.py [slug ...]
With no args, pulls all seed collections that have a Hood Market slug.
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

BUILD = os.path.expanduser("~/workspace/goals/launch-economics-data-tool/build")
DB = os.path.join(BUILD, "tracker.db")
BASE = "https://www.richart.app"
ZERO = "0x0000000000000000000000000000000000000000"


def fetch(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (tracker)"})
    for a in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            print(f"  fetch retry {a+1}: {e}", flush=True)
            time.sleep(2 ** a)
    return None


def clean(html):
    t = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\s+", " ", t).strip()


def approx_time(rel):
    """'2d ago' / '5h ago' / '30m ago' / 'just now' -> ISO UTC (approximate)."""
    now = datetime.now(timezone.utc)
    m = re.match(r"(\d+)\s*([mhd])\s*ago", rel)
    if m:
        n, u = int(m.group(1)), m.group(2)
        delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[u]
        return (now - delta).isoformat()
    return now.isoformat()


def parse_activity(html):
    """Return list of dicts: event, token_id, price_eth, seller, buyer, tx_hash, timestamp."""
    out = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    for r in rows[1:]:  # skip header
        cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(cells) < 6:
            continue
        event = clean(cells[0]).lower()
        if event not in ("sale", "mint"):
            continue
        item_href = re.findall(r'href="([^"]+)"', cells[1])
        token_id = item_href[0].rstrip("/").split("/")[-1] if item_href else None
        price_txt = clean(cells[2]).replace("ETH", "").strip()
        try:
            price = float(price_txt)
        except ValueError:
            continue
        seller_m = re.findall(r"/hood/profile/(0x[a-fA-F0-9]{40})", cells[3])
        buyer_m = re.findall(r"/hood/profile/(0x[a-fA-F0-9]{40})", cells[4])
        seller = seller_m[0] if seller_m else (ZERO if event == "mint" else None)
        buyer = buyer_m[0] if buyer_m else None
        if not buyer:
            continue
        tx_m = re.findall(r"blockscout\.com/tx/(0x[a-fA-F0-9]{64})", cells[5])
        tx_hash = tx_m[0] if tx_m else f"unknown-{token_id}-{price}"
        out.append({
            "event": event, "token_id": token_id, "price_eth": price,
            "seller": seller, "buyer": buyer, "tx_hash": tx_hash,
            "timestamp": approx_time(clean(cells[5])),
        })
    return out


def init_db():
    schema = open(os.path.join(BUILD, "schema.sql")).read()
    con = sqlite3.connect(DB)
    con.executescript(schema)
    return con


def touch_wallet(con, addr, ts):
    if not addr:
        return
    con.execute(
        """INSERT INTO wallets(address, first_seen, last_seen, tx_count)
           VALUES(?,?,?,1)
           ON CONFLICT(address) DO UPDATE SET
             last_seen=excluded.last_seen,
             tx_count=tx_count+1,
             first_seen=min(first_seen, excluded.first_seen)""",
        (addr, ts, ts),
    )


def main():
    slugs = sys.argv[1:] or [
        "conspiracy-narrative", "shithood", "slums-in-the-hood",
        "splitverse-panda", "surf-ace",
        # 2026-10-09: trimmed slugs whose Hood Market pages 404 (their tape
        # comes from OpenSea via pull_opensea.py): the-lil-wizards,
        # fireball-wizards, ccff00-161927574,
        # staccs-robinhood-homecoming-collection, robinhood-punks.
    ]
    con = init_db()
    total = 0
    for slug in slugs:
        row = con.execute("SELECT id FROM collections WHERE slug=?", (slug,)).fetchone()
        if row:
            cid = row[0]
        else:
            cur = con.execute(
                "INSERT INTO collections(slug, name, chain, launch_type) VALUES(?,?,?,?)",
                (slug, slug.replace("-", " ").title(), "robinhood", "unknown"),
            )
            cid = cur.lastrowid
        html = fetch(f"{BASE}/hood/collection/{slug}/activity")
        if not html:
            print(f"{slug}: fetch failed", flush=True)
            continue
        tape = parse_activity(html)
        new = 0
        for s in tape:
            try:
                con.execute(
                    """INSERT INTO sales(collection_id, tx_hash, token_id, price_eth,
                                        buyer, seller, timestamp, source)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (cid, s["tx_hash"], s["token_id"], s["price_eth"],
                     s["buyer"], s["seller"], s["timestamp"], "hood_market"),
                )
                new += 1
                touch_wallet(con, s["buyer"], s["timestamp"])
                touch_wallet(con, s["seller"], s["timestamp"])
            except sqlite3.IntegrityError:
                pass  # already have it
        con.commit()
        total += new
        print(f"{slug}: {len(tape)} rows on tape, {new} new", flush=True)
        time.sleep(2)  # gentle
    con.close()
    print(f"DONE: {total} new sales ingested")
    # heartbeat for the dashboard's "Data sources" section (never fails the run)
    try:
        _hp = os.path.expanduser("~/workspace/goals/launch-economics-data-tool/hidden_files/source_pulls.json")
        os.makedirs(os.path.dirname(_hp), exist_ok=True)
        try:
            _d = json.load(open(_hp))
        except Exception:
            _d = {}
        _d["hood_market"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        json.dump(_d, open(_hp, "w"), indent=1)
    except Exception as _e:
        print(f"  heartbeat warn: {_e}", flush=True)


if __name__ == "__main__":
    main()
