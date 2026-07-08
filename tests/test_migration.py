"""Migration tests — run the CSV import against the real backup and assert the
audited invariants (audit §4 + decisions D1/D2)."""
from datetime import date
from pathlib import Path

import pytest

from app.models import Match, MatchStatus, Payment, Player, Season, Signup, Team
from scripts.migrate_csv import migrate, parse_score

SOURCE = Path(__file__).resolve().parent.parent.parent / "cernyfoot" / "static"

pytestmark = pytest.mark.skipif(
    not (SOURCE / "users.csv").exists(), reason="original backup not present"
)


@pytest.fixture
def report(session):
    rep = migrate(SOURCE, session, today=date(2026, 7, 8))
    session.commit()
    return rep


def test_parse_score():
    assert parse_score("13:12") == (13, 12)
    assert parse_score("0:0") == (0, 0)
    assert parse_score("") is None
    assert parse_score("Nehralo sa") is None


def test_players_and_admins(report):
    # 22 registered players; phantom `nickname` header must not become a player.
    assert report["counts"]["players_registered"] == 22
    assert Player.query.filter_by(nickname="nickname").count() == 0
    # D1 — exactly these four admins.
    admins = {p.nickname for p in Player.query.filter_by(is_admin=True)}
    assert admins == {"berco", "frido", "michal", "tomasc"}


def test_drift_resolved_per_d2(report):
    assert {d["file"] for d in report["drift_resolutions"]} == {
        "2025-01-23.csv",
        "2025-03-06.csv",
    }
    m1 = Match.query.filter_by(date=date(2025, 1, 23)).one()
    assert (m1.green_score, m1.orange_score) == (8, 11)
    m2 = Match.query.filter_by(date=date(2025, 3, 6)).one()
    assert (m2.green_score, m2.orange_score) == (6, 3)


def test_match_statuses(report):
    # 16 cancelled dates in the source file.
    assert report["counts"]["matches_cancelled"] == 16
    assert Match.query.filter_by(status=MatchStatus.cancelled).count() == 16
    # Every played match has a result; no played match sits at 0:0 (audit §4).
    for m in Match.query.filter_by(status=MatchStatus.played):
        assert m.has_result
        assert (m.green_score, m.orange_score) != (0, 0)
    # The stray 19:00.csv was skipped.
    assert "19:00.csv" in report["skipped_files"]


def test_guests_excluded_from_registered(report):
    guests = Player.query.filter_by(is_guest=True).all()
    assert len(guests) == report["counts"]["players_guest"]
    # Guest signups carry the guest team marker.
    guest_signups = Signup.query.filter_by(team=Team.guest).count()
    assert guest_signups == 3  # audited count of Hosť rows


def test_signup_teams_match_audit_counts(report):
    # Counts per audit §4 (Zelená 222 · Oranžová 229 · Unassigned 56).
    assert Signup.query.filter_by(team=Team.green).count() == 222
    assert Signup.query.filter_by(team=Team.orange).count() == 229
    assert Signup.query.filter_by(team=Team.unassigned).count() == 56


def test_unassigned_only_in_cancelled(report):
    rows = (
        Signup.query.filter_by(team=Team.unassigned)
        .join(Match)
        .filter(Match.status != MatchStatus.cancelled)
        .count()
    )
    assert rows == 0


def test_payments(report):
    # Every registered (non-guest) player gets a payment row for 2025/2026.
    season = Season.query.filter_by(label="2025/2026").one()
    assert Payment.query.filter_by(season_id=season.id).count() == 22
    paid = Payment.query.filter_by(status="Vyplatené").count()
    assert paid == 6  # berco, petof, michal, frido, roman, tomasc
    # `rado` was missing from subscriptions.csv → defaulted with a warning.
    assert any("rado" in w for w in report["warnings"])


def test_idempotent_rerun(session, report):
    """Running the migration twice must not duplicate anything."""
    first_counts = dict(report["counts"])
    rep2 = migrate(SOURCE, session, today=date(2026, 7, 8))
    session.commit()
    assert rep2["counts"] == first_counts
    assert Player.query.count() == first_counts["players_registered"] + first_counts["players_guest"]
