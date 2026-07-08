"""Phase 6 tests: payments (self-view + admin matrix), registration with guest
upgrade, players page, landing page, form-strip history."""
from datetime import date, time, timedelta

import pytest

from app.models import Match, MatchStatus, Payment, Player, Season, Signup, Team
from app.services import stats as stats_svc

TODAY = date.today()


@pytest.fixture
def season(session):
    s = Season(label="s", starts_on=TODAY - timedelta(days=100),
               ends_on=TODAY + timedelta(days=100), match_weekday=3,
               match_start=time(19, 0), match_end=time(20, 0))
    session.add(s); session.commit()
    return s


@pytest.fixture
def admin(session):
    p = Player(nickname="sef", is_admin=True)
    p.set_password("x")
    session.add(p); session.commit()
    return p


@pytest.fixture
def player(session):
    p = Player(nickname="hrac")
    p.set_password("x")
    session.add(p); session.commit()
    return p


def login(client, nickname):
    return client.post("/auth/login", data={"nickname": nickname, "password": "x"},
                       follow_redirects=True)


# ---- Payments ----------------------------------------------------------------------

def test_my_payment_view(client, player, season, session):
    session.add(Payment(player_id=player.id, season_id=season.id, status="Vyplatené"))
    session.commit()
    login(client, "hrac")
    html = client.get("/payment").get_data(as_text=True)
    assert "Vyplatené" in html
    # No self-marking form exists (audit #12 closed).
    assert "Označiť ako" not in html and 'action="/payment"' not in html


def test_payment_requires_login(client, season):
    resp = client.get("/payment")
    assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]


def test_admin_payments_matrix(client, admin, player, season):
    login(client, "sef")
    # GET auto-enrols both players.
    html = client.get("/admin/payments").get_data(as_text=True)
    assert "hrac" in html and "sef" in html
    assert Payment.query.filter_by(season_id=season.id).count() == 2

    # Bulk update: mark hrac as paid.
    resp = client.post(
        "/admin/payments",
        data={"season": season.label, f"status_{player.id}": "Vyplatené",
              f"status_{admin.id}": "Nevyplatené"},
        follow_redirects=True,
    )
    assert "Uložené (1 zmien)" in resp.get_data(as_text=True)
    assert Payment.query.filter_by(player_id=player.id, season_id=season.id).one().status == "Vyplatené"


def test_admin_payments_requires_admin(client, player, season):
    login(client, "hrac")
    assert client.get("/admin/payments").status_code == 403


# ---- Registration ---------------------------------------------------------------------

def test_register_creates_player_and_payment(client, season):
    resp = client.post(
        "/auth/register",
        data={"nickname": "novacik", "name": "Jan", "surname": "Novy",
              "password": "h", "confirm": "h"},
        follow_redirects=True,
    )
    assert "Vitaj, novacik" in resp.get_data(as_text=True)
    p = Player.query.filter_by(nickname="novacik").one()
    assert p.is_claimed and not p.is_guest and p.name == "Jan"
    assert Payment.query.filter_by(player_id=p.id, season_id=season.id).count() == 1


def test_register_duplicate_nickname_refused(client, player, season):
    resp = client.post(
        "/auth/register",
        data={"nickname": "hrac", "password": "h", "confirm": "h"},
        follow_redirects=True,
    )
    assert "už existuje" in resp.get_data(as_text=True)


def test_register_upgrades_guest_and_keeps_history(client, season, session):
    guest = Player(nickname="miro", is_guest=True)
    session.add(guest); session.flush()
    m = Match(season_id=season.id, date=TODAY - timedelta(days=7),
              status=MatchStatus.played, green_score=5, orange_score=3)
    session.add(m); session.flush()
    session.add(Signup(match_id=m.id, player_id=guest.id, team=Team.green))
    session.commit()

    resp = client.post(
        "/auth/register",
        data={"nickname": "miro", "password": "h", "confirm": "h"},
        follow_redirects=True,
    )
    assert "Vitaj, miro" in resp.get_data(as_text=True)
    p = Player.query.filter_by(nickname="miro").one()
    assert not p.is_guest and p.is_claimed
    # History preserved — the win still counts.
    assert Signup.query.filter_by(player_id=p.id).count() == 1
    assert stats_svc.player_stats("miro", season)["wins_losses"][0] == 1


# ---- Pages ----------------------------------------------------------------------------

def test_players_page_public(client, player, admin, session):
    session.add(Player(nickname="duch", is_guest=True))
    session.commit()
    html = client.get("/players").get_data(as_text=True)
    assert "hrac" in html and "sef" in html
    assert "duch" not in html  # guests hidden


def test_landing_shows_upcoming(client, season, session):
    m = Match(season_id=season.id, date=TODAY + timedelta(days=5))
    session.add(m); session.commit()
    html = client.get("/").get_data(as_text=True)
    assert "Najbližší zápas" in html


def test_form_strip_history(client, player, season, session):
    for i, (g, o, team) in enumerate([(5, 3, Team.green), (2, 2, Team.green), (1, 4, Team.green)]):
        m = Match(season_id=season.id, date=TODAY - timedelta(days=7 * (3 - i)),
                  status=MatchStatus.played, green_score=g, orange_score=o)
        session.add(m); session.flush()
        session.add(Signup(match_id=m.id, player_id=player.id, team=team))
    session.commit()

    history = stats_svc.player_history("hrac", season)
    assert [h["result"] for h in history] == ["W", "D", "L"]

    login(client, "hrac")
    html = client.get("/my_stats").get_data(as_text=True)
    assert 'class="res res-w"' in html and 'class="res res-l"' in html
