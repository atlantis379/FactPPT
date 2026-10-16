"""Archive the brief and draft of every finished task into snapshot files, then shrink the database file.

The store does this on every write of a project anyway; run this once to shrink projects that are not being worked on.
usage: python tools/compact_projects.py [--data-root DIR] [--no-vacuum]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.deckflow import Store  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-root", type=Path, default=None, help="deckflow data root (default data/deckflow)")
    ap.add_argument("--no-vacuum", action="store_true", help="do not rewrite the database file afterwards")
    args = ap.parse_args()
    store = Store(args.data_root)
    with store.connect() as db:
        sizes = dict(db.execute("SELECT id, length(state) FROM workflows").fetchall())
    for wid, before in sizes.items():
        r = store.compact(wid)
        with store.connect() as db:
            after = db.execute("SELECT length(state) FROM workflows WHERE id=?", (wid,)).fetchone()[0]
        print(f"{wid}: archived {r['archived']} tasks, {before // 1024} KB -> {after // 1024} KB", flush=True)
    if not args.no_vacuum:
        before = store.database.stat().st_size
        db = sqlite3.connect(store.database)
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute("VACUUM")
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.close()
        print(f"database {before // 2**20} MB -> {store.database.stat().st_size // 2**20} MB")


if __name__ == "__main__":
    main()
