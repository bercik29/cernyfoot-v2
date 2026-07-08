"""Nightly SQLite backup with integrity verification and retention pruning.

Uses the sqlite3 online-backup API (safe while the app is running, WAL-friendly),
then runs PRAGMA integrity_check on the copy — a backup that doesn't restore is
not a backup (acceptance criterion 10).

Usage (PythonAnywhere daily Task):
    /home/bercik29/cernyfoot-v2/.venv/bin/python -m scripts.backup_db \
        --db /home/bercik29/cernyfoot-v2/instance/cernyfoot.db \
        --dest /home/bercik29/backups --keep 14
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PREFIX = "cernyfoot-"


def backup(db_path: Path, dest_dir: Path, keep: int, now: datetime | None = None) -> Path:
    """Copy db_path into dest_dir, verify it, prune to `keep` newest. Returns the
    backup path. Raises on any failure."""
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    dest_dir.mkdir(parents=True, exist_ok=True)

    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"{PREFIX}{stamp}.db"

    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        src.close()

    # Verify the copy actually restores.
    result = dst.execute("PRAGMA integrity_check").fetchone()[0]
    tables = dst.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    dst.close()
    if result != "ok" or tables == 0:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"backup failed verification: integrity={result}, tables={tables}")

    # Retention: keep the newest `keep` backups.
    backups = sorted(dest_dir.glob(f"{PREFIX}*.db"), reverse=True)
    for old in backups[keep:]:
        old.unlink()

    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="path to the live SQLite database")
    parser.add_argument("--dest", required=True, help="backup directory")
    parser.add_argument("--keep", type=int, default=14, help="backups to retain (default 14)")
    args = parser.parse_args()

    try:
        dest = backup(Path(args.db), Path(args.dest), args.keep)
    except Exception as exc:  # noqa: BLE001 — a cron task wants one clear line
        print(f"BACKUP FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"backup ok: {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
