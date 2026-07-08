"""Shared helpers: authorization decorator, safe redirects, audit logging."""
from __future__ import annotations

import json
from functools import wraps
from urllib.parse import urlparse

from flask import abort
from flask_login import current_user

from .extensions import db, login_manager
from .models import AuditLog


def admin_required(view):
    """Require a logged-in admin. Closes the original app's unprotected-route
    class of defects (audit #4, NEW-1) — every mutating admin view wears this."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def is_safe_url(target: str | None) -> bool:
    """Only allow same-app relative redirects for the ?next= parameter."""
    if not target:
        return False
    parsed = urlparse(target)
    return not parsed.netloc and not parsed.scheme and target.startswith("/")


def log_action(action: str, entity: str | None = None, payload: dict | None = None) -> None:
    """Append to the audit trail. Caller commits."""
    actor_id = current_user.id if current_user.is_authenticated else None
    db.session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity=entity,
            payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
        )
    )
