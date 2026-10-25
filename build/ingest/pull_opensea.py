#!/usr/bin/env python3
"""Pull sales tape from OpenSea API v2 into tracker.db.

Complements pull_tape.py (Hood Market). OpenSea carries the tape for
collections whose trading happens on OpenSea; on Robinhood Chain most volume
is on Hood Market, so expect thin results there — wire anyway for the future.

Usage: python3 pull_opensea.py
Reads slugs from the OS_SLUGS map below; matches to collections by slug.

Auth: uses the stored custom.opensea credential via the skill helper.
"""
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from opensea_auth import auth_request, read_json

BUILD = os.path.expanduser("~/workspace/goals/launch-economics-data-tool/build")
DB = os.path.join(BUILD, "tracker.db")
HOST = "api.opensea.io"  # auth handled by opensea_auth (env var OPENSEA_API_KEY)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"  # bot protection 403s the default UA

# OpenSea slug -> (display name, chain, contract). Verified 2026-10-01,
# plus 2026-10-04 (CCFF00, Stacc's Homecoming — large-supply tier coverage),
# plus 2026-10-06 (Fireball Wizards — Stacc's burn-mechanism spin-off),
# plus 2026-10-09 (wizard evolution chain: Lil/Spark/Phoenix — burn cohort).
OS_SLUGS = {
    "robinhood-punks": ("Robinhood Punks", "robinhood", "0xf08c6556"),
    "chibi-hood": ("Chibi Hood", "robinhood", "0x30ff3966"),
    "city-of-stonks": ("City of Stonks", "robinhood", "0x9b3f3088"),
    "cartoonals-classics": ("Cartoonals Classics", "robinhood", "0x562ea68b"),
    "ccff00-161927574": ("CCFF00", "robinhood", "0x505a22ff"),
    "staccs-robinhood-homecoming-collection": ("Stacc's Homecoming", "robinhood", "0x7c165ae6"),
    "fireball-wizards": ("Fireball Wizards", "robinhood", "0xf0545da454"),
    "the-lil-wizards": ("Lil Wizards", "robinhood", "0xf00fa5d5e1"),
    "spark-wizards-560723123": ("Spark Wizards", "robinhood", "0x5e48f2e5d8"),
    "phoenix-wizards": ("Phoenix Wizards", "robinhood", "0xdb65419505"),
}


def api_get(path, params):
    url = f"https://{HOST}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    auth_request(req)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return read_json(resp)


def fetch_sales(slug, max_pages=20, after=None):
    """Paginate sale events. Returns list of normalized sale dicts."""
    out, cursor, pages = [], None, 0
    while pages < max_pages:
        params = {"event_type": "sale", "limit": 50}
        if after:
            params["after"] = after
        if cursor:
            params["next"] = cursor
        try:
            d = api_get(f"/api/v2/events/collection/{slug}", params)
        except Exception as e:
            print(f"  {slug}: api error: {e}", flush=True)
            break
        for e in d.get("asset_events", []):
            pay = e.get("payment", {}) or {}
            nft = e.get("nft", {}) or {}
            try:
                qty = int(pay.get("quantity", 0))
                dec = int(pay.get("decimals", 18))
                price = qty / (10 ** dec)
            except (ValueError, TypeError):
                continue
            ts = e.get("event_timestamp")
            try:
                iso = datetime.fromtimestamp(int(ts), timezone.utc).isoformat()
            except (ValueError, TypeError):
                continue
            out.append({
                "token_id": str(nft.get("identifier")),
                "price_eth": price if pay.get("symbol") in ("ETH", "WETH") else None,
                "pay_symbol": pay.get("symbol"),
                "buyer": (e.get("buyer") or "").lower(),
                "seller": (e.get("seller") or "").lower(),
                "tx_hash": e.get("transaction") or "",
                "timestamp": iso,
            })
        cursor = d.get("next")
        pages += 1
        time.sleep(1.1)  # gentle on rate limits
        if not cursor:
            break
    return out


def main():
    con = sqlite3.connect(DB)
    total = 0
    # Universe: EVERY tracked collection, not just the current top-30.
    # (2026-10-25 fix: the top-30-only pull froze the tape of any collection
    # that rotated out of the window, and the Graveyard misread that coverage
    # gap as death. SKNOTS had 858 OpenSea sales in 14 days while listed dead.)
    slugs = {}
    for slug, name in con.execute("SELECT slug, name FROM collections"):
        slugs[slug] = (name, "robinhood", "")
    for s, v in OS_SLUGS.items():
        slugs.setdefault(s, v)
    print(f"universe: {len(slugs)} tracked collections (full tape coverage)", flush=True)
    for slug, (name, chain, _) in slugs.items():
        row = con.execute("SELECT id FROM collections WHERE slug=?", (slug,)).fetchone()
        if row:
            cid = row[0]
        else:
            cur = con.execute(
                "INSERT INTO collections(slug, name, chain, launch_type) VALUES(?,?,?,?)",
                (slug, name, chain, "unknown"),
            )
            cid = cur.lastrowid
        last = con.execute(
            "SELECT MAX(timestamp) FROM sales WHERE collection_id=?", (cid,)).fetchone()[0]
        after = None
        if last:
            try:
                from datetime import timedelta
                after = int((datetime.fromisoformat(last) - timedelta(days=2)).timestamp())
            except Exception:
                after = None
        else:
            # First pull for this collection: bound the history to 120 days
            # so a long-history collection cannot stall the daily run. The
            # Span column on the dashboard discloses the tape depth honestly.
            after = int(datetime.now(timezone.utc).timestamp()) - 120 * 86400
        sales = fetch_sales(slug, after=after)
        new = 0
        for s in sales:
            if not s["tx_hash"] or not s["buyer"]:
                continue
            try:
                con.execute(
                    """INSERT INTO sales(collection_id, tx_hash, token_id, price_eth,
                                        pay_symbol, buyer, seller, timestamp, source)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (cid, s["tx_hash"], s["token_id"], s["price_eth"],
                     s.get("pay_symbol"), s["buyer"], s["seller"], s["timestamp"], "opensea"),
                )
                new += 1
                for addr in (s["buyer"], s["seller"]):
                    if addr:
                        con.execute(
                            """INSERT INTO wallets(address, first_seen, last_seen, tx_count)
                               VALUES(?,?,?,1)
                               ON CONFLICT(address) DO UPDATE SET
                                 last_seen=excluded.last_seen, tx_count=tx_count+1,
                                 first_seen=min(first_seen, excluded.first_seen)""",
                            (addr, s["timestamp"], s["timestamp"]),
                        )
            except sqlite3.IntegrityError:
                pass
        con.commit()
        total += new
        print(f"{slug}: {len(sales)} events, {new} new", flush=True)
    con.close()
    print(f"DONE: {total} new OpenSea sales ingested")
    # heartbeat for the dashboard's "Data sources" section (never fails the run)
    try:
        _hp = os.path.expanduser("~/workspace/goals/launch-economics-data-tool/hidden_files/source_pulls.json")
        os.makedirs(os.path.dirname(_hp), exist_ok=True)
        try:
            _d = json.load(open(_hp))
        except Exception:
            _d = {}
        _d["opensea_sales"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        json.dump(_d, open(_hp, "w"), indent=1)
    except Exception as _e:
        print(f"  heartbeat warn: {_e}", flush=True)


if __name__ == "__main__":
    main()
