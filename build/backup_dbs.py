#!/usr/bin/env python3
"""Weekly local backups of the dashboard databases.

Writes gzip'd, date-stamped copies of econ.db and tracker.db into
hidden_files/backups/. LOCAL ONLY: these files must never be pushed to
the public water-dragon-dashboard repo (tracker.db carries 31k wallet
addresses and scores; the repo .gitignore excludes *.db for this reason).

Rotation: keep the newest 8 econ backups and the newest 2 tracker
backups (tracker gzips to ~21 MB). econ.db is verified after writing by
restoring the gzip and counting snapshot rows.

Run: python3 build/backup_dbs.py
"""
import gzip
import os
import sqlite3
import tempfile
from datetime import date

BASE = os.path.expanduser("~/workspace/goals/launch-economics-data-tool")
BUILD = os.path.join(BASE, "build")
OUT = os.path.join(BASE, "hidden_files", "backups")
KEEP = {"econ": 8, "tracker": 2}


def snapshot_copy(src_path):
    """Consistent copy of a sqlite db via the backup API (safe while the
    daily pipeline has the db open). Returns raw db bytes."""
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        tmp = f.name
    dst = sqlite3.connect(tmp)
    src.backup(dst)
    dst.close()
    src.close()
    with open(tmp, "rb") as f:
        data = f.read()
    os.unlink(tmp)
    return data


def rotate(name):
    files = sorted(
        f for f in os.listdir(OUT)
        if f.startswith(f"{name}-") and f.endswith(".db.gz")
    )
    while len(files) > KEEP[name]:
        os.unlink(os.path.join(OUT, files.pop(0)))


def main():
    os.makedirs(OUT, exist_ok=True)
    stamp = date.today().isoformat()
    for name in ("econ", "tracker"):
        data = snapshot_copy(os.path.join(BUILD, f"{name}.db"))
        out = os.path.join(OUT, f"{name}-{stamp}.db.gz")
        with gzip.open(out, "wb") as f:
            f.write(data)
        rotate(name)
        print(f"{name}: {out} ({os.path.getsize(out):,} bytes)", flush=True)
    # Verify the econ backup restores and holds the snapshot series.
    raw = gzip.decompress(open(os.path.join(OUT, f"econ-{stamp}.db.gz"), "rb").read())
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        f.write(raw)
        tmp = f.name
    con = sqlite3.connect(tmp)
    rows = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    rng = con.execute("SELECT MIN(date(ts)), MAX(date(ts)) FROM snapshots").fetchone()
    con.close()
    os.unlink(tmp)
    print(f"econ backup verified: {rows} snapshot rows, {rng[0]} to {rng[1]}", flush=True)
    print("BACKUP OK", flush=True)


if __name__ == "__main__":
    main()
