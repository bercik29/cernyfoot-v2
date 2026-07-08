"""Security acceptance tests (criteria 1 & 2 from the audit §9).

1. Zero unauthenticated mutating endpoints — enforced by walking the route table,
   so a future route added without @login_required/@admin_required fails CI.
2. CSRF enforced; production refuses to boot with the fallback secret key.
"""
import re

import pytest

from app import create_app
from app.config import ProdConfig
from app.extensions import db

# POST endpoints that are public BY DESIGN (they are how you obtain a session).
PUBLIC_POST_ENDPOINTS = {"auth.login", "auth.claim", "auth.register"}


def _url_for_rule(rule) -> str:
    """Build a concrete URL from a rule, substituting dummy parameters."""
    url = re.sub(r"<int:[^>]+>", "1", rule.rule)
    return re.sub(r"<[^>]+>", "x", url)


def test_no_unauthenticated_mutating_endpoints(app, client):
    """Every POST route outside the auth trio must bounce anonymous callers."""
    post_rules = [
        r
        for r in app.url_map.iter_rules()
        if "POST" in r.methods and r.endpoint not in PUBLIC_POST_ENDPOINTS
        and r.endpoint != "static"
    ]
    assert post_rules, "route table unexpectedly empty"

    for rule in post_rules:
        resp = client.post(_url_for_rule(rule))
        assert resp.status_code in (302, 403), (
            f"{rule.endpoint} ({rule.rule}) answered {resp.status_code} to an "
            f"anonymous POST — it must redirect to login or return 403"
        )
        if resp.status_code == 302:
            assert "/auth/login" in resp.headers["Location"], rule.endpoint


def test_all_post_endpoints_are_known(app):
    """Every public POST endpoint must be on the explicit allowlist — adding a new
    public mutating route requires consciously editing this test."""
    public = {"auth.login", "auth.claim", "auth.register"}
    assert PUBLIC_POST_ENDPOINTS == public


def test_csrf_enforced_when_enabled():
    app = create_app("test")
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        db.create_all()
        client = app.test_client()
        resp = client.post("/auth/login", data={"nickname": "x", "password": "y"})
        assert resp.status_code == 400  # CSRF token missing
        db.drop_all()


def test_prod_refuses_default_secret(monkeypatch):
    monkeypatch.setattr(ProdConfig, "SECRET_KEY", "dev-insecure-change-me")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("prod")


def test_prod_boots_with_real_secret(monkeypatch, tmp_path):
    monkeypatch.setattr(ProdConfig, "SECRET_KEY", "a-real-secret")
    monkeypatch.setattr(
        ProdConfig, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{tmp_path/'t.db'}"
    )
    app = create_app("prod")
    assert not app.config["DEBUG"]
