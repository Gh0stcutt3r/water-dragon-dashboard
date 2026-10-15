#!/usr/bin/env python3
"""Refresh the tracked universe from OpenSea's top collections by volume.

Calls /api/v2/collections/top (chains=robinhood) for 1d/7d/30d windows.
- Appends any new slugs to build/resolved.json (never removes; history
  feeds the dragon section and tier base rates).
- Writes hidden_files/top30.json with all three window rankings for the
  dashboard's toggles (default 7d).
- Records a heartbeat for the dashboard's Data sources section.

Run before collect.py in the daily cron.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from opensea_auth import auth_request, read_json

GOAL = os.path.expanduser("~/workspace/goals/launch-economics-data-tool")
BUILD = os.path.join(GOAL, "build")
RESOLVED = os.path.join(BUILD, "resolved.json")
OUT = os.path.join(GOAL, "hidden_files", "top30.json")
HEARTBEAT = os.path.join(GOAL, "hidden_files", "source_pulls.json")
HOST = "api.opensea.io"  # auth handled by opensea_auth (env var OPENSEA_API_KEY)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

WINDOWS = {
    "1d": "one_day_volume",
    "7d": "seven_days_volume",
    "30d": "thirty_days_volume",
}

# User-pinned slugs, appended to every window after the API ranking. These stay
# tracked even when outside the top 30 by volume.
# 2026-10-12: abstract-workers (friend's launch, 1,111 supply, Robinhood Chain).
PINNED = ["abstract-workers"]


def api_get(path, params):
    url = f"https://{HOST}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    auth_request(req)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return read_json(resp)


def main():
    windows = {}
    seen = {}  # slug -> name
    for win, sort_by in WINDOWS.items():
        try:
            d = api_get("/api/v2/collections/top",
                        {"chains": "robinhood", "sort_by": sort_by, "limit": 30})
        except Exception as e:
            print(f"  {win}: fetch failed: {e}", flush=True)
            continue
        slugs = []
        for c in d.get("collections", []):
            slug = c.get("collection")
            if not slug:
                continue
            slugs.append(slug)
            seen[slug] = c.get("name") or slug
        windows[win] = slugs
        print(f"  {win}: {len(slugs)} collections", flush=True)
        time.sleep(1)

    if not windows.get("7d"):
        print("ABORT: no 7d ranking; leaving universe unchanged", flush=True)
        sys.exit(1)

    # Append pinned slugs to every window (tracked at user request even when
    # outside the top 30 by volume).
    for slug in PINNED:
        if slug not in seen:
            seen[slug] = slug.replace("-", " ").title()
        for win in windows:
            if slug not in windows[win]:
                windows[win].append(slug)
    print(f"pinned: {PINNED}", flush=True)

    # Update resolved.json: append new slugs, never remove.
    try:
        resolved = json.load(open(RESOLVED))
    except Exception:
        resolved = {}
    added = 0
    for slug, name in seen.items():
        if slug in resolved or any(
                isinstance(v, dict) and v.get("slug") == slug for v in resolved.values()):
            continue
        # Fetch supply for the new entry (bounded: new slugs only).
        supply = None
        try:
            info = api_get(f"/api/v2/collections/{slug}", {})
            supply = info.get("total_supply")
            time.sleep(0.4)
        except Exception as e:
            print(f"  info fetch failed for {slug}: {e}", flush=True)
        resolved[name] = {"slug": slug, "verified_name": name,
                          "chain": "robinhood", "total_supply": supply}
        added += 1
    json.dump(resolved, open(RESOLVED, "w"), indent=2)
    print(f"resolved.json: {len(resolved)} entries ({added} new)", flush=True)

    # Write the window rankings for the dashboard.
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "windows": windows}, open(OUT, "w"), indent=1)
    print(f"wrote {OUT}", flush=True)

    # Heartbeat.
    try:
        hb = json.load(open(HEARTBEAT))
    except Exception:
        hb = {}
    hb["universe"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump(hb, open(HEARTBEAT, "w"), indent=1)


if __name__ == "__main__":
    main()
