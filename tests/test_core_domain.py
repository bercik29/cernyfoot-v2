"""Phase 3 tests: timing service, schedule generation, signup/signout, cancellation,
season admin. Route tests use matches dated relative to real today so no time
mocking is needed; deadline edges are unit-tested with fixed datetimes."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.extensions import db
from app.models import Holiday, Match, MatchStatus, Player, Season, Signup, Team
from app.services import seasons as seasons_svc
from app.services import timing
from app.services.schedule import generate_schedule

TZ = ZoneInfo("Europe/Bratislava")
TODAY = date.today()


@pytest.fixture
def season(session):
    s = Season(
        label="test-season",
        starts_on=TODAY - timedelta(days=120),
        ends_on=TODAY + timedelta(days=120),
        match_weekday=3,
        match_start=time(19, 0),
        match_end=time(20, 0),
    )
    session.add(s)
    session.commit()
    return s


@pytest.fixture
def player(session):
    p = Player(nickname="hrac")
    p.set_password("x")
    session.add(p)
    session.commit()
    return p


@pytest.fixture
def admin(session):
    p = Player(nickname="sef", is_admin=True)
    p.set_password("x")
    session.add(p)
    session.commit()
    return p


def login(client, nickname):
    return client.post(
        "/auth/login", data={"nickname": nickname, "password": "x"}, follow_redirects=True
    )


# ---- Timing (single deadline — kills NEW-2) -----------------------------------

def test_deadline_and_lock_from_config(app, season, session):
    m = Match(season_id=season.id, date=date(2026, 3, 5))
    session.add(m); session.commit()

    deadline = timing.signup_deadline(m.date)
    lock = timing.match_lock(m.date)
    assert (deadline.hour, deadline.minute) == (18, 45)
    assert (lock.hour, lock.minute) == (19, 5)

    before = datetime(2026, 3, 5, 18, 44, tzinfo=TZ)
    between = datetime(2026, 3, 5, 18, 50, tzinfo=TZ)
    after_lock = datetime(2026, 3, 5, 19, 6, tzinfo=TZ)

    assert timing.is_signup_open(m, before)
    assert not timing.is_signup_open(m, between)   # closed for signup...
    assert not timing.is_over(m.date, between)     # ...but not yet history
    assert timing.is_over(m.date, after_lock)

    m.status = MatchStatus.cancelled
    assert not timing.is_signup_open(m, before)  # cancelled is never open


# ---- Schedule generation --------------------------------------------------------

def test_generate_schedule_weekday_holidays_idempotent(app, season, session):
    # A holiday covering one would-be match day.
    first_matchday = season.starts_on + timedelta(
        days=(3 - season.starts_on.weekday()) % 7
    )
    holiday_day = first_matchday + timedelta(days=14)
    session.add(Holiday(date_from=holiday_day, date_to=holiday_day, kind="public",
                        description="Sviatok"))
    session.commit()

    report = generate_schedule(season)
    db.session.commit()

    created = report["created"]
    assert len(created) > 20
    assert all(d.weekday() == 3 for d in created)          # Thursdays only
    assert holiday_day not in created
    assert [d for d, _ in report["skipped_holiday"]] == [holiday_day]

    # Cancel one match, then regenerate: nothing new, cancelled stays cancelled.
    cancelled = Match.query.filter_by(date=created[0]).one()
    cancelled.status = MatchStatus.cancelled
    db.session.commit()

    report2 = generate_schedule(season)
    db.session.commit()
    assert report2["created"] == []
    assert report2["skipped_existing"] == len(created)
    assert Match.query.filter_by(date=created[0]).one().status == MatchStatus.cancelled


# ---- Season resolution (fixes NEW-9) ------------------------------------------

def test_season_resolve_off_season(app, session):
    old = Season(label="a", starts_on=date(2023, 9, 1), ends_on=date(2024, 6, 30))
    new = Season(label="b", starts_on=date(2024, 9, 1), ends_on=date(2025, 6, 30))
    session.add_all([old, new]); session.commit()

    s, off = seasons_svc.resolve(today=date(2024, 10, 1))
    assert s.label == "b" and not off
    s, off = seasons_svc.resolve(today=date(2025, 8, 1))   # summer break
    assert s.label == "b" and off                            # latest by DATE + flagged
    s, off = seasons_svc.resolve(label="a")
    assert s.label == "a" and not off


# ---- Signup / signout ---------------------------------------------------------------

@pytest.fixture
def open_match(season, session):
    m = Match(season_id=season.id, date=TODAY + timedelta(days=7))
    session.add(m); session.commit()
    return m


@pytest.fixture
def past_match(season, session):
    m = Match(season_id=season.id, date=TODAY - timedelta(days=7))
    session.add(m); session.commit()
    return m


def test_signup_and_signout(client, player, open_match):
    login(client, "hrac")
    resp = client.post(f"/match/{open_match.id}/signup", follow_redirects=True)
    assert "Prihlásený na" in resp.get_data(as_text=True)
    assert Signup.query.filter_by(match_id=open_match.id, player_id=player.id).count() == 1

    # Duplicate signup is a no-op.
    client.post(f"/match/{open_match.id}/signup", follow_redirects=True)
    assert Signup.query.filter_by(match_id=open_match.id).count() == 1

    resp = client.post(f"/match/{open_match.id}/signout", follow_redirects=True)
    assert "Odhlásený zo zápasu" in resp.get_data(as_text=True)
    assert Signup.query.filter_by(match_id=open_match.id).count() == 0


def test_signup_closed_after_deadline(client, player, past_match):
    login(client, "hrac")
    resp = client.post(f"/match/{past_match.id}/signup", follow_redirects=True)
    assert "uzavreté" in resp.get_data(as_text=True)
    assert Signup.query.count() == 0


def test_signup_requires_login(client, open_match):
    resp = client.post(f"/match/{open_match.id}/signup")
    assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]


def test_calendar_shows_upcoming_and_counts(client, player, season, open_match, past_match):
    past_match.status = MatchStatus.played
    past_match.green_score, past_match.orange_score = 10, 8
    db.session.commit()

    login(client, "hrac")
    client.post(f"/match/{open_match.id}/signup")
    html = client.get("/calendar").get_data(as_text=True)
    assert "Najbližší zápas" in html
    assert "Prihlásených" in html and ">1</span>" in html
    assert "Si prihlásený" in html
    # Past result renders as a scoreboard row (green and orange spans).
    assert '<span class="g">10</span>' in html and '<span class="o">8</span>' in html
    assert "data-deadline=" in html  # live countdown target rendered


# ---- Cancellation (kills NEW-3) --------------------------------------------------

def test_cancel_effective_immediately(client, admin, player, season, open_match):
    login(client, "sef")
    resp = client.post(f"/admin/matches/{open_match.id}/cancel", follow_redirects=True)
    assert "zrušený" in resp.get_data(as_text=True)
    assert open_match.status == MatchStatus.cancelled

    # Immediately reflected on the calendar (no restart, no cache).
    html = client.get("/calendar").get_data(as_text=True)
    assert "Zrušené" in html or "Nehralo sa" in html

    # And signup is refused.
    login(client, "hrac")
    client.post(f"/match/{open_match.id}/signup", follow_redirects=True)
    assert Signup.query.count() == 0


def test_cancel_requires_admin(client, player, open_match):
    login(client, "hrac")
    assert client.post(f"/admin/matches/{open_match.id}/cancel").status_code == 403


def test_restore_cancelled_match(client, admin, open_match, session):
    open_match.status = MatchStatus.cancelled
    session.commit()
    login(client, "sef")
    client.post(f"/admin/matches/{open_match.id}/restore", follow_redirects=True)
    assert open_match.status == MatchStatus.scheduled


def test_played_match_cannot_be_cancelled(client, admin, past_match, session):
    past_match.status = MatchStatus.played
    past_match.green_score, past_match.orange_score = 5, 4
    session.commit()
    login(client, "sef")
    resp = client.post(f"/admin/matches/{past_match.id}/cancel", follow_redirects=True)
    assert "nedá zrušiť" in resp.get_data(as_text=True)
    assert past_match.status == MatchStatus.played


# ---- Season & holiday admin (acceptance criterion 5) ---------------------------

def test_create_season_and_generate_from_ui(client, admin):
    login(client, "sef")
    resp = client.post(
        "/admin/seasons",
        data={
            "label": "2026/2027",
            "starts_on": "2026-09-17",
            "ends_on": "2027-06-30",
            "match_weekday": "3",
            "match_start": "19:00",
            "match_end": "20:00",
        },
        follow_redirects=True,
    )
    assert "2026/2027 vytvorená" in resp.get_data(as_text=True)
    s = Season.query.filter_by(label="2026/2027").one()

    # Add Christmas break via UI, then generate.
    client.post(
        "/admin/holidays",
        data={"date_from": "2026-12-21", "date_to": "2027-01-08",
              "kind": "school", "description": "Vianočné prázdniny"},
        follow_redirects=True,
    )
    resp = client.post(f"/admin/seasons/{s.id}/generate", follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert "Vygenerovaných" in body

    matches = Match.query.filter_by(season_id=s.id).all()
    assert len(matches) > 30
    assert all(m.date.weekday() == 3 for m in matches)
    xmas = [m for m in matches if date(2026, 12, 21) <= m.date <= date(2027, 1, 8)]
    assert xmas == []


def test_duplicate_season_label_rejected(client, admin, season):
    login(client, "sef")
    resp = client.post(
        "/admin/seasons",
        data={"label": "test-season", "starts_on": "2030-09-01", "ends_on": "2031-06-30",
              "match_weekday": "3", "match_start": "19:00", "match_end": "20:00"},
        follow_redirects=True,
    )
    assert "už existuje" in resp.get_data(as_text=True)
    assert Season.query.filter_by(label="test-season").count() == 1


def test_admin_pages_require_admin(client, player):
    login(client, "hrac")
    for path in ("/admin/", "/admin/seasons", "/admin/holidays", "/admin/matches"):
        assert client.get(path).status_code == 403, path
