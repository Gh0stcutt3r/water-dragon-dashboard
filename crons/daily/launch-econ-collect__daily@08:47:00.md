---
id: launch-econ-collect
title: Launch-econ daily collection (Robinhood)
enabled: true
owner: goal:launch-economics-data-tool
mode: task
schedule:
  kind: daily
  timezone: America/New_York
  time: 08:47:00
delivery:
  - chat_id: e0bac0ed-21f8-4109-94fc-a7073f4ef24c
metadata:
  tags: [cron:flexible-time]
  originating_chat_context_json: '{"chat_id":"e0bac0ed-21f8-4109-94fc-a7073f4ef24c","origin_provider":"main","chat_kind":"direct","event_kind":"message","require_mention":false,"device_id":"287d0484-88cb-335d-247f-b4445f837ba7"}'
  presentation_locale: en-US
---
Daily data-collection run for the Robinhood Chain launch-economics tracker (goal: launch-economics-data-tool, v0.4 Part 2 — "Dragon Dashboard").

Do this:
1. Run `python3 ~/workspace/goals/launch-economics-data-tool/build/refresh_universe.py` first. It pulls OpenSea's top 30 Robinhood collections by 7d ETH volume (plus 1d/30d windows), appends user-pinned slugs (see PINNED in that script — tracked at the user's request even when outside the top 30) to each window, appends new slugs to `build/resolved.json` (never removes), and writes `hidden_files/top30.json`. Confirm exit 0.
2. Run `python3 ~/workspace/goals/launch-economics-data-tool/build/ingest/collect_snapshots.py` and confirm it completes (exit 0, snapshots written to `build/econ.db`). It snapshots the current top-30 slugs from `hidden_files/top30.json`.
3. Run the v0.4 tape pipeline (OpenSea only — the Hood Market pull was retired 2026-10-11 after 8 days with zero new sales; its 762 historical rows remain in tracker.db untouched):
   - `python3 ~/workspace/goals/launch-economics-data-tool/build/ingest/pull_opensea.py`
   - `python3 ~/workspace/goals/launch-economics-data-tool/build/ingest/pull_mints.py` (mint prices via OpenSea mint events + Robinhood RPC tx values; user-approved 2026-10-14; writes collections.mint_price_eth; free mints = 0)
   - `python3 ~/workspace/goals/launch-economics-data-tool/build/detect/patterns.py`
   - `python3 ~/workspace/goals/launch-economics-data-tool/build/wallets/score.py`
   - `python3 ~/workspace/goals/launch-economics-data-tool/build/reports/dashboard.py`
   Confirm each exits 0. The dashboard regenerates at `workspace/goals/launch-economics-data-tool/files/dragon-dashboard.html`.
4. Run the wizard-family volume trigger: `python3 ~/workspace/goals/launch-economics-data-tool/build/detect/wizard_watch.py` (user-approved 2026-10-13, backs the Stacc hold recommendation's "revisit if volume returns" trigger). If it prints "WIZARD_WATCH: quiet", stay silent. If it reports activity, relay its output briefly to the main chat.
5. Stay silent on success — this is background dataset accumulation, no chat report needed — except for a wizard_watch activity report from step 4.
6. If any step fails or writes zero new rows, report the failure briefly to the main chat with the error output.

Do not run analysis on a schedule; analysis happens on demand when the user asks.
