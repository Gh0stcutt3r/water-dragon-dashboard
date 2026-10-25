# Launch economics data tool

Goal ID: goal_de96324ea735
Goal slug: launch-economics-data-tool

## Description
Ghostcutter's own runnable version of the NFT Launch Economics Engine concept his developer friend specced: pulls and analyzes NFT launch data over time, broken into supply-size categories (sub-1k, 1k–2k, 2k–3k, and so on). Seeded with the 31 Robinhood Chain collections from the friend's dataset; serves both as buy-side intelligence for the $20 experiment and pricing input for his own collection launch.

## Status notes
- 2026-10-25: Tape-coverage fix. pull_opensea.py previously pulled sales only for the current top-30 (7d), so any collection rotating out had its tape frozen while snapshots continued; the new Graveyard tab read that silence as death (8 of its 12 "dead" were live, incl. SKNOTS with 858 sales in 14d). Pull now covers every tracked collection daily with a per-collection watermark (last sale minus 2d; first pulls bounded to 120d). Backfill took the tape from 74,014 to 133,793 sales; verified dead list is 4 (Slums In The Hood, Shithood, Splitverse Panda, Surf Ace). 8 slugs have no OpenSea tape: Cartoonals (pre-mint), Chog Genesis slug mislabeled "Yield Fields Deed" in the tracker (renamed), a malformed Yield Fields duplicate, Chibi Hood / City of Stonks / Phoenix Wizards (zero OpenSea sales ever), and mineland-rh / vault-street-rh (404 on OpenSea). The real Yield Field Deeds is slug yield-field-deeds, fully covered.
