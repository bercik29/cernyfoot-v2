"""Golden-master parity (acceptance criterion 6).

Migrates the real backup into the test DB, runs the v2 stats engine, and compares
every metric against the frozen output of the ORIGINAL statistics.py
(scripts/output/golden_master.json — drift-corrected per D2, empty past match
auto-cancelled).

Comparison notes:
  * exact for scalars/tuples/tables; pytest.approx for floats;
  * top-3 lists whose ties the original ordered non-deterministically (set
    iteration) are compared as value-sequences + agreement on shared players;
  * `most_frequent_team` ties are compared by count.
"""
import json
from datetime import date
from pathlib import Path

import pytest

from app.models import Season
from app.services import stats as stats_svc
from scripts.migrate_csv import migrate

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT.parent / "cernyfoot" / "static"
GOLDEN_PATH = ROOT / "scripts" / "output" / "golden_master.json"

pytestmark = pytest.mark.skipif(
    not (SOURCE / "users.csv").exists() or not GOLDEN_PATH.exists(),
    reason="original backup or golden master not present",
)

GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8")) if GOLDEN_PATH.exists() else {}
SEASON_LABELS = ["2024/2025", "2025/2026"]


@pytest.fixture
def migrated(session):
    migrate(SOURCE, session, today=date(2026, 7, 8))
    session.commit()


def v2_global(label):
    season = Season.query.filter_by(label=label).one()
    return stats_svc.global_stats(season)


def approx_deep(a, b, path=""):
    """Recursive comparison: floats approx, lists/tuples element-wise."""
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        assert len(a) == len(b), f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            approx_deep(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert a == pytest.approx(b), f"{path}: {a} != {b}"
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


def assert_top3_equiv(golden, mine, path):
    """Value sequences must match; shared players must have identical values."""
    gv = sorted((v for _, v in golden), reverse=True)
    mv = sorted((v for _, v in mine), reverse=True)
    assert gv == pytest.approx(mv), f"{path}: value sequences differ: {gv} vs {mv}"
    gmap, mmap = dict(golden), dict(mine)
    for player in set(gmap) & set(mmap):
        assert gmap[player] == pytest.approx(mmap[player]), f"{path}: {player}"


TIE_UNSTABLE = {
    "top_3_highest_attendance",
    "top_3_lowest_attendance",
    "top_3_most_wins",
    "top_3_most_losses",
    "top_3_longest_winning_streaks",
    "top_3_longest_losing_streaks",
    "highest_efficiency",
}


@pytest.mark.parametrize("label", SEASON_LABELS)
def test_global_parity(migrated, label):
    golden = GOLDEN["seasons"][label]["global"]
    mine = v2_global(label)

    # Matches universe: golden lists filenames, v2 lists ISO dates.
    assert [f[:-4] for f in golden["all_matches"]] == mine["all_matches"]

    # Cancelled: count + the exact date set.
    g_count, g_dates = golden["total_matches_cancelled"]
    m_count, m_dates = mine["total_matches_cancelled"]
    assert (g_count, sorted(g_dates)) == (m_count, sorted(m_dates))

    # Deterministic metrics — exact/approx.
    for key in [
        "total_matches_played",
        "draws",
        "total_goals_scored",
        "average_goals_per_match",
        "top_scoring_team",
        "highest_scoring_match",
        "average_players_per_match",
        "most_frequent_number_of_players_per_match",
        "highest_number_of_players_per_match",
        "lowest_number_of_players_per_match",
    ]:
        approx_deep(golden[key], list(mine[key]) if isinstance(mine[key], tuple) else mine[key],
                    f"{label}.{key}")

    # Full appearance list — order-insensitive exact mapping.
    assert dict((tuple(x) for x in golden["most_frequent_players"])) == dict(
        mine["most_frequent_players"]
    )

    # League table — the headline metric. Exact, including guest rows.
    assert golden["all_players_stats"] == mine["all_players_stats"]

    # Tie-unstable top-3s.
    for key in TIE_UNSTABLE:
        assert_top3_equiv(
            [tuple(x) for x in golden[key]], mine[key], f"{label}.{key}"
        )

    # Most frequent 3-player combo — compare the count (ties arbitrary).
    if golden["most_frequent_team"]:
        assert golden["most_frequent_team"][0][1] == mine["most_frequent_team"][0][1]
    else:
        assert mine["most_frequent_team"] == []


@pytest.mark.parametrize("label", SEASON_LABELS)
def test_player_parity(migrated, label):
    """All 12 personal metrics, all 22 registered players, exact (approx floats)."""
    season = Season.query.filter_by(label=label).one()
    golden_players = GOLDEN["seasons"][label]["players"]
    assert len(golden_players) == 22

    for nickname, golden in golden_players.items():
        mine = stats_svc.player_stats(nickname, season)
        for key, g_val in golden.items():
            m_val = mine[key]
            if isinstance(m_val, tuple):
                m_val = list(m_val)
            approx_deep(g_val, m_val, f"{label}.{nickname}.{key}")


def test_league_table_totals_sane(migrated):
    """Cross-check: league table games sum == sum of players-per-match."""
    for label in SEASON_LABELS:
        mine = v2_global(label)
        total_games = sum(r["games_played"] for r in mine["all_players_stats"].values())
        played = mine["total_matches_played"][0]
        assert total_games == pytest.approx(mine["average_players_per_match"] * played)


def test_stats_pages_render(migrated, client, session):
    """The /stats and /my_stats pages render with real migrated data."""
    html = client.get("/stats?season=2024/2025").get_data(as_text=True)
    assert "Tabuľka" in html and "Zelení vs Oranžoví" in html
    assert "510" in html  # total goals 2024/2025

    # my_stats requires login → claim berco and check his page.
    from app.models import Player
    berco = Player.query.filter_by(nickname="berco").one()
    berco.set_password("x")
    session.commit()
    client.post("/auth/login", data={"nickname": "berco", "password": "x"})
    html = client.get("/my_stats?season=2024/2025").get_data(as_text=True)
    assert "Moje výsledky · berco" in html and "Série" in html
