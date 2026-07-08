"""Backup script tests: copy verifies, retention prunes, corruption fails loudly."""
import sqlite3
from datetime import datetime

import pytest

from scripts.backup_db import backup


@pytest.fixture
def live_db(tmp_path):
    db = tmp_path / "live.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE players (id INTEGER PRIMARY KEY, nickname TEXT)")
    con.execute("INSERT INTO players (nickname) VALUES ('berco')")
    con.commit()
    con.close()
    return db


def test_backup_creates_verified_copy(live_db, tmp_path):
    dest = backup(live_db, tmp_path / "backups", keep=5)
    assert dest.exists()
    con = sqlite3.connect(str(dest))
    assert con.execute("SELECT nickname FROM players").fetchone()[0] == "berco"
    con.close()


def test_retention_prunes_oldest(live_db, tmp_path):
    dest_dir = tmp_path / "backups"
    stamps = [datetime(2026, 7, d, 3, 0, 0) for d in range(1, 6)]
    for s in stamps:
        backup(live_db, dest_dir, keep=3, now=s)
    remaining = sorted(p.name for p in dest_dir.glob("cernyfoot-*.db"))
    assert len(remaining) == 3
    assert remaining[0] == "cernyfoot-20260703-030000.db"  # oldest two pruned


def test_missing_db_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup(tmp_path / "nope.db", tmp_path / "backups", keep=3)


def test_empty_db_fails_verification(tmp_path):
    empty = tmp_path / "empty.db"
    sqlite3.connect(str(empty)).close()  # zero tables
    with pytest.raises(RuntimeError, match="verification"):
        backup(empty, tmp_path / "backups", keep=3)
    assert not list((tmp_path / "backups").glob("*.db"))  # bad copy removed
