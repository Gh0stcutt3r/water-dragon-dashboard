#!/usr/bin/env python3
"""Snapshot collector — Robinhood Chain launch economics.

Reads the collection registry (resolved.json: name -> slug), pulls
per-collection info and stats via OpenSea API v2, and appends one
timestamped snapshot row per collection into econ.db (SQLite, append-only).

Supply tiers: sub-1k | 1k-2k | 2k-3k | 3k-5k | 5k-10k | 10k+ | unknown
Collections without a resolved slug are skipped (kept in resolved.json with
slug=null so nothing is silently dropped).

Auth: portable via opensea_auth (OPENSEA_API_KEY env var for public use).

Run after refresh_universe.py in the daily pipeline.
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

BUILD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOLVED = os.path.join(BUILD, "resolved.json")
DB = os.path.join(BUILD, "econ.db")
HEARTBEAT = os.path.join(os.path.dirname(BUILD), "hidden_files", "source_pulls.json")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"  # bot protection 403s the default UA


def tier(supply):
    if not supply or supply <= 0:
        return "unknown"
    if supply < 1000:
        return "sub-1k"
    if supply < 2000:
        return "1k-2k"
    if supply < 3000:
        return "2k-3k"
    if supply < 5000:
        return "3k-5k"
    if supply < 10000:
        return "5k-10k"
    return "10k+"


def get(path):
    url = f"https://api.opensea.io{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    try:
        auth_request(req)
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = read_json(resp)
        return d if isinstance(d, dict) else None
    except Exception as e:
        print(f"  api error {path}: {e}", flush=True)
        return None


def main():
    resolved = json.load(open(RESOLVED))
    # Prefer the current top-30 (refreshed daily by refresh_universe.py);
    # fall back to the full registry on first run or refresh failure.
    top30_path = os.path.join(os.path.dirname(BUILD), "hidden_files", "top30.json")
    try:
        top30 = json.load(open(top30_path))["windows"]["7d"]
        by_slug = {}
        for name, meta in resolved.items():
            if isinstance(meta, dict) and meta.get("slug"):
                by_slug[meta["slug"]] = (name, meta)
        resolved = {by_slug[s][0]: by_slug[s][1] for s in top30 if s in by_slug}
        # Any top-30 slug missing from the registry gets a minimal entry so it
        # is not silently skipped.
        for s in top30:
            if s not in by_slug:
                resolved[s] = {"slug": s, "verified_name": s, "chain": "robinhood",
                               "total_supply": None}
        print(f"universe: top-30 refresh ({len(resolved)} slugs)", flush=True)
    except Exception as e:
        print(f"top30.json unreadable ({e}); using full registry", flush=True)
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS snapshots(
        ts TEXT, name TEXT, slug TEXT, tier TEXT,
        total_supply INTEGER, num_owners INTEGER,
        floor REAL, floor_sym TEXT, volume REAL, vol_sym TEXT,
        sales INTEGER, avg_price REAL, category TEXT)""")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok, skipped = 0, []
    for name, meta in resolved.items():
        slug = meta.get("slug")
        if not slug:
            skipped.append(name)
            continue
        info = get(f"/api/v2/collections/{slug}")
        time.sleep(0.4)
        stats = get(f"/api/v2/collections/{slug}/stats")
        time.sleep(0.4)
        if not info or not stats:
            skipped.append(f"{name} (api)")
            continue
        t = (stats.get("total") or {})
        supply = info.get("total_supply")
        cur.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            ts, name, slug, tier(supply), supply,
            t.get("num_owners"), t.get("floor_price"), t.get("floor_price_symbol"),
            t.get("volume"), t.get("volume_symbol"), t.get("sales"),
            t.get("average_price"), info.get("category")))
        ok += 1
        print(f"  snap {name:24s} tier={tier(supply):8s} supply={supply} "
              f"owners={t.get('num_owners')} floor={t.get('floor_price')}", flush=True)
    con.commit()
    con.close()
    print(f"\n[{ts}] wrote {ok} snapshots; skipped: {skipped}")
    # heartbeat for the dashboard's "Data sources" section (never fails the run)
    try:
        os.makedirs(os.path.dirname(HEARTBEAT), exist_ok=True)
        try:
            _d = json.load(open(HEARTBEAT))
        except Exception:
            _d = {}
        _d["opensea_snapshots"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        json.dump(_d, open(HEARTBEAT, "w"), indent=1)
    except Exception as _e:
        print(f"  heartbeat warn: {_e}", flush=True)


if __name__ == "__main__":
    main()
