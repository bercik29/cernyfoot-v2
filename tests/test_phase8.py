"""Phase 8 tests: automatic holiday generation, manual match creation, and the
admin dashboard payments link."""
from datetime import date, time, timedelta

import pytest

from app.models import Holiday, Match, Player, Season
from app.services.holidays import easter_sunday, public_holidays, seed_school_year

TODAY = date.today()


# ---- Easter & public holidays (exact math) ------------------------------------

def test_easter_known_dates():
    assert easter_sunday(2024) == date(2024, 3, 31)
    assert easter_sunday(2025) == date(2025, 4, 20)
    assert easter_sunday(2026) == date(2026, 4, 5)
    assert easter_sunday(2027) == date(2027, 3, 28)


def test_public_holidays_2026():
    days = dict(public_holidays(2026))
    assert date(2026, 4, 3) in days     # Good Friday
    assert date(2026, 4, 6) in days     # Easter Monday
    assert date(2026, 9, 15) in days
    assert date(2026, 12, 24) in days
    assert len(days) == 14              # 12 fixed + 2 Easter-based


def test_seed_school_year_matches_original_2025(session):
    """The generator must reproduce the original app's hand-written 2025/2026
    entries for the dates that matter (Easter break was 2.–7.4.2026)."""
    report = seed_school_year(2025)
    session.commit()
    assert report["created"] > 0

    school = {(h.date_from, h.date_to) for h in Holiday.query.filter_by(kind="school")}
    assert (date(2025, 10, 30), date(2025, 10, 31)) in school      # jesenné
    assert (date(2025, 12, 22), date(2026, 1, 7)) in school        # vianočné
    assert (date(2026, 4, 2), date(2026, 4, 7)) in school          # veľkonočné — exact
    assert report["spring_estimate"] is not None                    # jarné flagged

    publics = {h.date_from for h in Holiday.query.filter_by(kind="public")}
    assert date(2025, 11, 17) in publics
    assert date(2026, 4, 3) in publics                              # Good Friday
    # Out-of-school-year holidays are not seeded.
    assert date(2025, 5, 1) not in publics


def test_seed_school_year_idempotent(session):
    r1 = seed_school_year(2026)
    session.commit()
    r2 = seed_school_year(2026)
    session.commit()
    assert r2["created"] == 0
    assert r2["skipped"] == r1["created"]


# ---- Routes ------------------------------------------------------------------------

@pytest.fixture
def admin(session):
    p = Player(nickname="sef", is_admin=True)
    p.set_password("x")
    session.add(p); session.commit()
    return p


@pytest.fixture
def season(session):
    s = Season(label="s", starts_on=TODAY - timedelta(days=100),
               ends_on=TODAY + timedelta(days=100), match_weekday=3,
               match_start=time(19, 0), match_end=time(20, 0))
    session.add(s); session.commit()
    return s


def login(client, nickname):
    return client.post("/auth/login", data={"nickname": nickname, "password": "x"},
                       follow_redirects=True)


def test_generate_holidays_route(client, admin):
    login(client, "sef")
    resp = client.post("/admin/holidays/generate", data={"school_year": "2026"},
                       follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert "Vygenerovaných" in body and "ODHAD" in body
    assert Holiday.query.count() > 10

    resp = client.post("/admin/holidays/generate", data={"school_year": "banana"},
                       follow_redirects=True)
    assert "platný rok" in resp.get_data(as_text=True)


def test_add_match_route(client, admin, season):
    login(client, "sef")
    target = (TODAY + timedelta(days=3)).isoformat()

    resp = client.post("/admin/matches/add", data={"date": target}, follow_redirects=True)
    assert "pridaný" in resp.get_data(as_text=True)
    assert Match.query.filter_by(date=TODAY + timedelta(days=3)).count() == 1

    # Duplicate refused.
    resp = client.post("/admin/matches/add", data={"date": target}, follow_redirects=True)
    assert "už zápas existuje" in resp.get_data(as_text=True)
    assert Match.query.count() == 1

    # Outside any season refused.
    outside = (TODAY + timedelta(days=365)).isoformat()
    resp = client.post("/admin/matches/add", data={"date": outside}, follow_redirects=True)
    assert "nepatrí do žiadnej sezóny" in resp.get_data(as_text=True)

    # Garbage refused.
    resp = client.post("/admin/matches/add", data={"date": "nonsense"}, follow_redirects=True)
    assert "platný dátum" in resp.get_data(as_text=True)


def test_add_match_requires_admin(client, season, session):
    p = Player(nickname="hrac"); p.set_password("x")
    session.add(p); session.commit()
    login(client, "hrac")
    assert client.post("/admin/matches/add", data={"date": TODAY.isoformat()}).status_code == 403


def test_dashboard_links_payments(client, admin, season):
    login(client, "sef")
    html = client.get("/admin/").get_data(as_text=True)
    assert "/admin/payments" in html  # the missing link, now present
    assert "/admin/holidays" in html and "/admin/matches" in html
