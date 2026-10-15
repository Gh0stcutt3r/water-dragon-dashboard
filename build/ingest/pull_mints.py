#!/usr/bin/env python3
"""Pull mint prices for tracked collections into tracker.db.

OpenSea's activity tab shows mint prices, but its public events API returns
mint events WITHOUT a payment field. The workaround (verified 2026-10-14):
each mint event carries its transaction hash, and the transaction's native
ETH value on the Robinhood RPC is the mint payment. Per-token price =
tx_value / tokens minted in that tx. The mode across sampled mints is the
collection's mint price (uniform for nearly all launches; free mints
correctly resolve to 0).

Robinhood Chain only, so native ETH is the payment token (user-confirmed
2026-10-14; no ERC20 parsing needed).

Usage: python3 pull_mints.py
Reads slugs from hidden_files/top30.json (7d window), same universe as
pull_opensea.py. Writes collections.mint_price_eth.

Auth: uses the stored custom.opensea credential via the skill helper.
"""
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from opensea_auth import auth_request, read_json

BUILD = os.path.expanduser("~/workspace/goals/launch-economics-data-tool/build")
DB = os.path.join(BUILD, "tracker.db")
HOST = "api.opensea.io"  # auth handled by opensea_auth (env var OPENSEA_API_KEY)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"  # bot protection 403s the default UA
RPC = "https://rpc.mainnet.chain.robinhood.com"

MAX_PAGES = 10       # 500 mint events per collection max; enough for a mode
RPC_BATCH = 50       # tx lookups per batch JSON-RPC call


def api_get(path, params):
    url = f"https://{HOST}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    auth_request(req)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return read_json(resp)


def fetch_mint_events(slug):
    """Paginate mint events. Returns list of (tx_hash, token_id)."""
    out, cursor, pages = [], None, 0
    while pages < MAX_PAGES:
        params = {"event_type": "mint", "limit": 50}
        if cursor:
            params["next"] = cursor
        try:
            d = api_get(f"/api/v2/events/collection/{slug}", params)
        except Exception as e:
            print(f"  {slug}: api error: {e}", flush=True)
            break
        for e in d.get("asset_events", []):
            tx = e.get("transaction") or ""
            nft = e.get("nft", {}) or {}
            if tx:
                out.append((tx, str(nft.get("identifier"))))
        cursor = d.get("next")
        pages += 1
        time.sleep(1.1)  # gentle on rate limits
        if not cursor:
            break
    return out


def rpc_batch_tx_values(tx_hashes):
    """Batch eth_getTransactionByHash. Returns {tx_hash: value_eth}."""
    out = {}
    hashes = list(tx_hashes)
    for i in range(0, len(hashes), RPC_BATCH):
        chunk = hashes[i:i + RPC_BATCH]
        payload = json.dumps([
            {"jsonrpc": "2.0", "id": j, "method": "eth_getTransactionByHash",
             "params": [h]} for j, h in enumerate(chunk)
        ]).encode()
        req = urllib.request.Request(
            RPC, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                results = json.loads(resp.read())
        except Exception as e:
            print(f"  rpc batch error: {e}", flush=True)
            continue
        if isinstance(results, dict):
            results = [results]
        for j, r in enumerate(results):
            tx = (r.get("result") or {})
            val = tx.get("value")
            if val:
                try:
                    out[chunk[j]] = int(val, 16) / 1e18
                except (ValueError, TypeError):
                    pass
        time.sleep(0.3)
    return out


def resolve_mint_price(slug):
    """Returns (mint_price_eth, sample_mints) or (None, 0)."""
    events = fetch_mint_events(slug)
    if not events:
        return None, 0
    per_tx = defaultdict(list)
    for tx, tok in events:
        per_tx[tx].append(tok)
    values = rpc_batch_tx_values(per_tx.keys())
    prices = []
    for tx, toks in per_tx.items():
        if tx in values:
            # per-token price for this tx (handles batch mints)
            prices.append(round(values[tx] / len(toks), 6))
    if not prices:
        return None, 0
    mode_price, count = Counter(prices).most_common(1)[0]
    return mode_price, len(prices)


def main():
    con = sqlite3.connect(DB)
    top30_path = os.path.expanduser(
        "~/workspace/goals/launch-economics-data-tool/hidden_files/top30.json")
    try:
        top_slugs = json.load(open(top30_path))["windows"]["7d"]
        print(f"universe: top-30 ({len(top_slugs)} slugs)", flush=True)
    except Exception as e:
        print(f"top30.json unreadable ({e}); aborting", flush=True)
        return
    updated, skipped = 0, 0
    for slug in top_slugs:
        row = con.execute(
            "SELECT id, mint_price_eth FROM collections WHERE slug=?", (slug,)).fetchone()
        if row:
            cid, existing = row
        else:
            cur = con.execute(
                "INSERT INTO collections(slug, name, chain, launch_type) VALUES(?,?,?,?)",
                (slug, slug, "robinhood", "unknown"))
            cid, existing = cur.lastrowid, None
        # Refresh if never priced; re-check quarterly otherwise (mint price
        # is immutable post-launch, so this is cheap insurance, not a rescan).
        price, n = resolve_mint_price(slug)
        if price is None:
            print(f"{slug}: no mint events found", flush=True)
            skipped += 1
            continue
        con.execute(
            "UPDATE collections SET mint_price_eth=? WHERE id=?", (price, cid))
        con.commit()
        updated += 1
        prev = f" (was {existing})" if existing is not None and existing != price else ""
        print(f"{slug}: mint {price} ETH from {n} txs{prev}", flush=True)
    con.close()
    print(f"DONE: {updated} mint prices set, {skipped} without mint data")
    try:
        _hp = os.path.expanduser(
            "~/workspace/goals/launch-economics-data-tool/hidden_files/source_pulls.json")
        os.makedirs(os.path.dirname(_hp), exist_ok=True)
        try:
            _d = json.load(open(_hp))
        except Exception:
            _d = {}
        _d["opensea_mints"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        json.dump(_d, open(_hp, "w"), indent=1)
    except Exception as _e:
        print(f"  heartbeat warn: {_e}", flush=True)


if __name__ == "__main__":
    main()
