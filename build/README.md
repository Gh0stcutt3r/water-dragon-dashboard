# Dragon Dashboard — tracker build (v0.4 Part 2, 2026-10-01)

Tape-first post-launch tracker + wallet intelligence for the Launch Economics Engine.

## Layout
- `schema.sql` — SQLite schema (collections, sales, snapshots, events, wallets, wallet_scores)
- `config.yaml` — seed collections, detection thresholds
- `tracker.db` — the dataset (gitignored in spirit; lives here)
- `ingest/pull_tape.py` — Hood Market activity scraper → sales (keyless)
- `detect/patterns.py` — sweep / whale_dump / wash_flag / volume_spike / ♘ trojan_horse detectors → events
- `wallets/score.py` — dive track records, win rates, realized PnL, dump counts → wallet_scores

## Pipeline
```
python3 ingest/pull_tape.py [slug ...]   # Hood Market tape (default: all HM seed slugs)
python3 ingest/pull_opensea.py           # OpenSea tape (OS_SLUGS in script)
python3 detect/patterns.py
python3 wallets/score.py --top 10
```
Runs daily via the `launch-econ-collect` cron (08:47 EDT), which also still runs
the legacy `~/workspace/onchain-experiment/launch-econ/collect.py`.

## Status
- 9 collections, 1,761 sales (761 Hood Market + 1,000 OpenSea), 674 wallets scored.
- Detectors finding real patterns (e.g., the 0x6e93…4f6d SLUMS sweep).
- Wallet ≠ person: sybil/bot noise is real; scores are signals, not identities.

## OpenSea findings (2026-10-01)
- Auth works via stored `custom.opensea` credential (X-API-KEY header).
  api.opensea.io 403s Python-urllib's default User-Agent — browser-like UA required.
- OpenSea indexes Robinhood Chain collections (metadata + contracts) but carries
  almost no Robinhood sale tape — trading happens on Hood Market. robinhood-punks
  was the exception (1,000 sales pulled); city-of-stonks, cartoonals-classics,
  chibi-hood returned zero events and are wired for future activity.
- Resolved Robinhood contracts: city-of-stonks 0x9b3f3088…7769d,
  cartoonals-classics 0x562ea68b…75a41, chibi-hood 0x30ff3966…,
  robinhood-punks 0xf08c6556…

## Open
- Dashboard view — not yet built.
- Backfill depth: OpenSea puller caps at 20 pages/run; Hood Market shows recent
  tape only. Deep history accrues via the daily cron.
