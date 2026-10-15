# NFT Launch Economics Engine — v0.4 Spec Addition
## Part 2: Post-Launch Tracking & Estimation Feedback Loop

**Status:** Draft for review (Ghostcutter, 2026-10-01)
**Relation to v0.3:** Extends the existing three layers (pre-mint pricing engine, market benchmarking, performance feedback). This spec defines the **performance feedback layer** as a first-class tracking module and wires it back into the estimator.

---

## 1. Purpose

Track launched collections over time — starting with 24-hour volume, then daily pulls — to detect patterns in buys, sales, volume, floor sweeps, and whale dumps. Observed outcomes feed back into the pre-mint estimator as calibrated base rates, so every tracked launch makes the next estimate smarter.

Design principle: **the feedback loop is the product.** A pricing calculator plus a separate tracker is two tools; one system where estimates are scored against actuals is the moat.

## 2. Data model

### 2.1 Collection registry (shared with Part 1)
One registry, used by both the estimator and the tracker:
- Contract address, chain, launch date, launch type (free mint / fixed-price mint / auction / stealth)
- Supply, mint price (0 for free mints), creator/owner addresses
- Category tags (see §5)

### 2.2 Daily snapshots (time series)
One row per collection per day:
- Floor price, 24h sales count, 24h volume, **median sale price**
- Listed % (supply overhang), unique owners, unique buyers/sellers (24h)
- Top offer / bid depth where available

### 2.3 Event log (tape-derived)
Detected from the sales tape, never from floor snapshots alone:
- **Floor sweep:** >N sales to a single buyer within one window (configurable, default 5)
- **Whale dump:** a top-20 holder lists or sells a large position
- **Wash pattern:** circular trading between linked wallets (flag, don't accuse — mark confidence)
- **Mint-out:** time-to-sellout for mint-phase tracking
- **Volume spike:** 24h sales ≥3× trailing-7-day average
- **♘ Trojan horse:** sweep (apparent demand) followed by a dump from the same wallet, 1–72h later — the gift that was an exit

### 2.4 Estimate-vs-actual log
Every pre-mint estimate is recorded with its inputs; when the launch is tracked, actuals are joined to it. Calibration error is tracked per estimator version so v0.4 → v0.5 improvements are measurable.

## 3. Ingestion

### 3.1 Backfill (cold-start fix)
Stability patterns need months of history. Do not wait — on first run, backfill historical sales for seed collections via OpenSea / Reservoir APIs. Target: ≥12 months of history for ≥50 collections before the tracker is considered calibrated.

### 3.2 Ongoing pulls
- Daily cron per tracked collection (24h window metrics)
- Heavier intra-day polling only for collections in active mint phase or under alert
- All pulls append-only; never overwrite history

### 3.3 Tape-first rule
Every derived metric (momentum, sweeps, dumps, stability) is computed from the **sales tape**: per-sale price, buyer, seller, timestamp. Floor price is a lagging snapshot and must never be the sole input to a pattern detector. (Lesson learned the hard way: a flat floor can hide +35% tape movement.)

## 4. Pattern detection

### 4.1 Short-term (trading signals)
- Buy/sell pressure: newest-vs-oldest price direction over 24h/7d windows
- Sweep vs organic: buyer concentration ratio per window
- Liquidity health: consecutive zero-sale days, bid depth trend

### 4.2 Long-term (stability — the underexplored half)
Nobody tracks this well; it is the estimator's most valuable input:
- **Survival curves:** P(floor ≥ mint price) at day 30 / 60 / 90 / 180, by cohort
- **Holder retention:** % of minters still holding at day 30 / 90
- **Listing drift:** listed % trend — rising listings signal holder exodus
- **Volume decay:** half-life of daily volume post-mint

## 5. Category taxonomy

Start from OpenSea's native categories, then subdivide wherever price dynamics split. OpenSea's "Art" is too broad — a 1/1 and a 10k PFP drop share nothing economically.

Proposed level-2 tags (extensible):
- Generative art / PFP / 1-of-1 / Photography / Music / Gaming assets / Membership / Domain-like

Each tag carries its own cohort statistics (§6). New tags are added only when ≥10 tracked collections qualify — no thin cohorts.

## 6. Feedback loop (tracker → estimator)

For each cohort defined by **(category × launch type × chain)**:
- Mint-out probability and median time-to-mint-out
- Survival base rates at 30/60/90/180 days
- Median ROI at each horizon (for paid mints); median time-to-first-profitable-exit (for free mints)
- Wash/sweep incidence rate (risk flag)

The estimator consumes these as **priors**. A new estimate = cohort base rate adjusted by collection-specific signals, with the base rate cited explicitly (provenance policy from v0.3 applies: every number shows its source cohort and sample size).

## 7. Mint-date timing module

Uses tracker data + ecosystem calendar to recommend launch windows:
- **Day-of-week / seasonality effects** mined from historical mint performance
- **Holiday dead zones** (e.g., late December) flagged automatically
- **Ecosystem calendar overlay:** user-supplied major events (chain upgrades, big mints like Unvault's Bugz) — launches are scored against proximity to these
- **Market regime indicator:** chain-wide NFT volume trend (rising / flat / falling) as a go/no-go input

## 8. Data sources (initial)

| Source | Use | Key needed |
|---|---|---|
| OpenSea API | Historical + ongoing sales, listings, offers | Yes (free signup) |
| Reservoir API | Backfill alternative, multi-chain | Yes (free tier) |
| Blockscout / chain explorers | On-chain sale verification, wash forensics | No (public REST) |
| Marketplace page scrapes (e.g., Hood Market) | Chains without good API coverage | No, but fragile |

## 9. Constraints (carried from v0.3)

- **T0 methodology, six rules** — unchanged; Part 2 outputs are labeled with the same methodology version as the estimates they calibrate.
- **Provenance/anti-bias policies** — every cohort stat shows sample size and date range; no cherry-picked windows; wash-flagged volume is reported separately, never silently included.
- **No invented data** — gaps are labeled as gaps, not interpolated.

## 10. Build order

1. **Tracker module first:** registry + ingestion + snapshots + basic charts. (Simpler half; useful standalone.)
2. **Pattern detectors second:** sweeps, dumps, wash flags, stability curves.
3. **Feedback loop third:** cohort stats → estimator priors + estimate-vs-actual scoring.
4. **Timing module last:** needs the stability data from steps 1–2 to be meaningful.

---

*Next: review, then hand to implementation. Open question for v0.4 review: minimum cohort size (proposed 10) and sweep threshold defaults.*

**Build status (2026-10-01):** Zen built the working v0.4 tracker with the user: SQLite dataset (`build/tracker.db`), Hood Market tape ingestor (keyless), pattern detectors (sweep/whale-dump/wash-flag/volume-spike), and wallet intelligence (dive track records, win rates, realized PnL, dump counts). Live on 5 Hood Market collections, 761 sales ingested; daily cron (`launch-econ-collect`, 08:47 EDT) runs the full pipeline. Blocked: OpenSea API key (user to provide via secure entry) for non-Hood-Market collections (Wolves, Chibi, CCFF00, Sloppies, City of Stonks…); dashboard view not yet built.
