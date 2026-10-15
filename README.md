# Water Dragon Dashboard

A tape-first NFT launch tracker for Robinhood Chain. It watches the top 30
collections by trading volume, scores wallet behavior, detects unusual
trading patterns, recovers mint prices from on-chain data, and renders it
all as a single self-contained HTML dashboard.

Built to answer one question before a launch: **what do successful launches
on this chain actually look like?**

## What it does

- **Universe refresh** (`build/refresh_universe.py`): pulls OpenSea's top
  Robinhood collections by 7d ETH volume (1d/7d/30d windows) every morning.
- **Snapshots** (`build/ingest/collect_snapshots.py`): records floor,
  volume, owners, and supply tiers per collection into `econ.db`.
- **Sales tape** (`build/ingest/pull_opensea.py`): ingests individual sale
  events into `tracker.db`.
- **Mint prices** (`build/ingest/pull_mints.py`): recovers what each
  collection actually minted for. OpenSea's mint events carry no price, so
  the script reads each mint transaction's native ETH value from the
  Robinhood RPC. Free mints resolve to 0.
- **Pattern detection** (`build/detect/patterns.py`): flags sweeps, whale
  dumps, wash-trading signals, and volume spikes.
- **Wallet scoring** (`build/wallets/score.py`): tracks diver win rates and
  realized PnL. Wallet ≠ person; treat scores as signals, not identities.
- **Dashboard** (`build/reports/dashboard.py`): renders everything into one
  offline HTML file with 1d/7d/30d toggles, per-collection cards (floor,
  volume, mint price), and a launch-tier briefing.

## Setup

1. Get a free OpenSea API key: https://docs.opensea.io/reference/api-keys
2. `export OPENSEA_API_KEY=<your key>`
3. `python3 build/refresh_universe.py`
4. `python3 build/ingest/collect_snapshots.py`
5. `python3 build/ingest/pull_opensea.py`
6. `python3 build/ingest/pull_mints.py`
7. `python3 build/detect/patterns.py`
8. `python3 build/wallets/score.py`
9. `python3 build/reports/dashboard.py`
10. Open `files/dragon-dashboard.html` in a browser.

Python 3 only, standard library only. No dependencies to install.

## Scheduling

The pipeline is designed to run once daily (morning, before you check it).
Any scheduler works; cron example:

```
47 8 * * * cd /path/to/repo && python3 build/refresh_universe.py && \
  python3 build/ingest/collect_snapshots.py && \
  python3 build/ingest/pull_opensea.py && \
  python3 build/ingest/pull_mints.py && \
  python3 build/detect/patterns.py && \
  python3 build/wallets/score.py && \
  python3 build/reports/dashboard.py
```

## Data honesty

- The tape is OpenSea events only. Mints that bypass OpenSea still resolve
  because mint price comes from the chain, not the marketplace.
- Mint price is the mode across sampled mint transactions (native ETH
  only; this tracker covers Robinhood Chain exclusively).
- USD labels on OpenSea for Robinhood Chain are unreliable; all values are
  read and stored in ETH.
- Wash flags are investigative, never accusations.

## License

MIT. See LICENSE.
