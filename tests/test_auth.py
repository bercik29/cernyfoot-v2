"""Phase 2 auth tests: claim flow (D3), login, logout, admin reset, rate limit."""
import pytest

from app.extensions import db, limiter
from app.models import AuditLog, Player


@pytest.fixture
def players(session):
    """One unclaimed player, one claimed player, one guest, one admin."""
    unclaimed = Player(nickname="novy")
    claimed = Player(nickname="hrac")
    claimed.set_password("tajne")
    guest = Player(nickname="rudo", is_guest=True)
    admin = Player(nickname="sef", is_admin=True)
    admin.set_password("sefheslo")
    session.add_all([unclaimed, claimed, guest, admin])
    session.commit()
    return {"unclaimed": unclaimed, "claimed": claimed, "guest": guest, "admin": admin}


def login(client, nickname, password):
    return client.post(
        "/auth/login", data={"nickname": nickname, "password": password}, follow_redirects=True
    )


# ---- Claim flow (D3) -------------------------------------------------------------

def test_unclaimed_login_redirects_to_claim(client, players):
    resp = client.post(
        "/auth/login", data={"nickname": "novy", "password": "whatever"}
    )
    assert resp.status_code == 302
    assert "/auth/claim/novy" in resp.headers["Location"]


def test_claim_sets_password_and_logs_in(client, players, session):
    resp = client.post(
        "/auth/claim/novy",
        data={"password": "x", "confirm": "x"},  # any non-empty password (D3)
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Vitaj, novy" in resp.get_data(as_text=True)
    p = Player.query.filter_by(nickname="novy").one()
    assert p.is_claimed and p.check_password("x")
    assert AuditLog.query.filter_by(action="auth.claim").count() == 1


def test_claim_rejects_empty_and_mismatched(client, players):
    resp = client.post("/auth/claim/novy", data={"password": "", "confirm": ""})
    assert not Player.query.filter_by(nickname="novy").one().is_claimed
    resp = client.post("/auth/claim/novy", data={"password": "a", "confirm": "b"})
    assert "Heslá sa nezhodujú" in resp.get_data(as_text=True)
    assert not Player.query.filter_by(nickname="novy").one().is_claimed


def test_claimed_account_cannot_be_reclaimed(client, players):
    resp = client.post(
        "/auth/claim/hrac", data={"password": "hack", "confirm": "hack"}, follow_redirects=True
    )
    assert "už má heslo" in resp.get_data(as_text=True)
    assert Player.query.filter_by(nickname="hrac").one().check_password("tajne")


def test_guest_cannot_claim_or_login(client, players):
    resp = client.post(
        "/auth/claim/rudo", data={"password": "x", "confirm": "x"}, follow_redirects=True
    )
    assert "Neznáma prezývka" in resp.get_data(as_text=True)
    resp = login(client, "rudo", "x")
    assert "Neznáma prezývka" in resp.get_data(as_text=True)


# ---- Login / logout ---------------------------------------------------------------

def test_login_success_and_logout(client, players):
    resp = login(client, "hrac", "tajne")
    assert "hrac" in resp.get_data(as_text=True)
    resp = client.post("/auth/logout", follow_redirects=True)
    assert "Odhlásený" in resp.get_data(as_text=True)


def test_login_wrong_password(client, players):
    resp = login(client, "hrac", "zle")
    assert "Nesprávne heslo" in resp.get_data(as_text=True)


def test_login_unknown_nickname(client, players):
    resp = login(client, "nikto", "x")
    assert "Neznáma prezývka" in resp.get_data(as_text=True)


def test_next_redirect_must_be_relative(client, players):
    resp = client.post(
        "/auth/login?next=https://evil.example/",
        data={"nickname": "hrac", "password": "tajne"},
    )
    assert resp.status_code == 302
    assert "evil.example" not in resp.headers["Location"]


# ---- Admin reset ---------------------------------------------------------------------

def test_reset_requires_admin(client, players):
    target_id = players["claimed"].id
    # Anonymous → redirected to login.
    resp = client.post(f"/auth/reset/{target_id}")
    assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]
    # Non-admin → 403.
    login(client, "hrac", "tajne")
    assert client.post(f"/auth/reset/{target_id}").status_code == 403


def test_admin_reset_unclaims_account(client, players):
    target_id = players["claimed"].id
    login(client, "sef", "sefheslo")
    resp = client.post(f"/auth/reset/{target_id}", follow_redirects=True)
    assert "zresetované" in resp.get_data(as_text=True)
    p = db.session.get(Player, target_id)
    assert not p.is_claimed
    assert AuditLog.query.filter_by(action="auth.password_reset").count() == 1


# ---- Rate limiting (D3 guardrail) ---------------------------------------------------

def test_login_rate_limit(app, client, players):
    app.config["LOGIN_RATELIMIT"] = "3 per minute"
    limiter.reset()
    for _ in range(3):
        resp = client.post("/auth/login", data={"nickname": "hrac", "password": "zle"})
        assert resp.status_code == 200
    resp = client.post("/auth/login", data={"nickname": "hrac", "password": "zle"})
    assert resp.status_code == 429
    limiter.reset()
