"""Phase 0 smoke tests: the app boots, routes respond, models work."""
from datetime import date, time

from app.models import (
    AuditLog,
    Holiday,
    Match,
    MatchStatus,
    Payment,
    Player,
    Season,
    Signup,
    Team,
)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Fodbal" in resp.get_data(as_text=True)


def test_404(client):
    assert client.get("/does-not-exist").status_code == 404


def test_password_hashing_roundtrip():
    p = Player(nickname="tester")
    assert not p.is_claimed
    p.set_password("hunter2")
    assert p.is_claimed
    assert p.check_password("hunter2")
    assert not p.check_password("wrong")
    # Hash must not be the plaintext (argon2 → starts with $argon2).
    assert p.password_hash.startswith("$argon2")


def test_full_schema_persists(session):
    s = Season(label="2025/2026", starts_on=date(2025, 9, 18), ends_on=date(2026, 6, 30))
    session.add(s)
    session.flush()

    m = Match(season_id=s.id, date=date(2025, 9, 25), status=MatchStatus.played,
              green_score=13, orange_score=12)
    p = Player(nickname="berco", is_admin=True)
    session.add_all([m, p])
    session.flush()

    session.add(Signup(match_id=m.id, player_id=p.id, team=Team.green))
    session.add(Payment(player_id=p.id, season_id=s.id, status="Vyplatené"))
    session.add(Holiday(date_from=date(2025, 12, 24), date_to=date(2026, 1, 7), kind="school"))
    session.add(AuditLog(actor_id=p.id, action="test.write", entity="smoke"))
    session.commit()

    assert m.has_result and m.score_str == "13:12"
    assert Signup.query.count() == 1
    assert Payment.query.filter_by(status="Vyplatené").count() == 1


def test_signup_uniqueness(session):
    import pytest
    from sqlalchemy.exc import IntegrityError

    s = Season(label="x", starts_on=date(2025, 9, 1), ends_on=date(2026, 6, 1))
    session.add(s); session.flush()
    m = Match(season_id=s.id, date=date(2025, 10, 2))
    p = Player(nickname="dup")
    session.add_all([m, p]); session.flush()

    session.add(Signup(match_id=m.id, player_id=p.id))
    session.commit()
    session.add(Signup(match_id=m.id, player_id=p.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
