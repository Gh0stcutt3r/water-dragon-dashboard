-- Launch Economics Tracker v0.4 — SQLite schema
-- Tape-first: sales is the source of truth; snapshots/events/wallet stats derive from it.

CREATE TABLE IF NOT EXISTS collections (
    id              INTEGER PRIMARY KEY,
    slug            TEXT UNIQUE NOT NULL,          -- marketplace slug
    name            TEXT NOT NULL,
    chain           TEXT NOT NULL DEFAULT 'robinhood',
    contract_address TEXT,
    launch_date     TEXT,                           -- ISO date, when known
    launch_type     TEXT,                           -- free_mint | fixed_mint | auction | unknown
    supply          INTEGER,
    mint_price_eth  REAL,
    category_tags   TEXT,                           -- comma-separated level-2 tags
    added_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sales (
    id              INTEGER PRIMARY KEY,
    collection_id   INTEGER NOT NULL REFERENCES collections(id),
    tx_hash         TEXT NOT NULL,
    token_id        TEXT,
    price_eth       REAL NOT NULL,
    buyer           TEXT NOT NULL,
    seller          TEXT NOT NULL,
    timestamp       TEXT NOT NULL,                  -- ISO UTC
    source          TEXT NOT NULL,                  -- hood_market | opensea | blockscout
    UNIQUE(collection_id, tx_hash, token_id)
);
CREATE INDEX IF NOT EXISTS idx_sales_coll_time ON sales(collection_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_sales_buyer ON sales(buyer);
CREATE INDEX IF NOT EXISTS idx_sales_seller ON sales(seller);

CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY,
    collection_id   INTEGER NOT NULL REFERENCES collections(id),
    date            TEXT NOT NULL,                  -- YYYY-MM-DD
    floor_eth       REAL,
    sales_24h       INTEGER,
    volume_24h_eth  REAL,
    median_sale_eth REAL,
    listed_pct      REAL,
    owners          INTEGER,
    UNIQUE(collection_id, date)
);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY,
    collection_id   INTEGER NOT NULL REFERENCES collections(id),
    type            TEXT NOT NULL,                  -- sweep | whale_dump | wash_flag | volume_spike | mint_out
    timestamp       TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 1.0,     -- 0..1; wash flags < 1.0
    details         TEXT NOT NULL                   -- JSON blob
);
CREATE INDEX IF NOT EXISTS idx_events_coll_type ON events(collection_id, type);

-- Wallet intelligence: derived from sales. Wallet != person (sybil noise is real);
-- track records are signals, not identities.
CREATE TABLE IF NOT EXISTS wallets (
    address         TEXT PRIMARY KEY,
    first_seen      TEXT,
    last_seen       TEXT,
    tx_count        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS wallet_scores (
    wallet          TEXT PRIMARY KEY REFERENCES wallets(address),
    dives           INTEGER NOT NULL DEFAULT 0,    -- buys within 7d of collection launch
    dive_wins       INTEGER NOT NULL DEFAULT 0,    -- dives later sold above buy price
    win_rate        REAL,                           -- dive_wins / dives
    realized_pnl_eth REAL NOT NULL DEFAULT 0,      -- sells minus buys where both observed
    dumps           INTEGER NOT NULL DEFAULT 0,    -- panic-dump pattern sells
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
