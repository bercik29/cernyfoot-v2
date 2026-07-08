"""Authentication: login, first-login claim flow (D3), logout, admin password reset.

Flow: a migrated player has no password (`is_claimed == False`). On their first
login attempt they are routed to the claim page, set any non-empty password
(argon2-hashed), and are logged in. Admins can reset a password, which returns
the account to the unclaimed state for re-claiming.
"""
from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db, limiter
from ..models import Payment, Player
from ..services import seasons as seasons_svc
from ..utils import admin_required, is_safe_url, log_action, safe_referrer
from . import bp
from .forms import ClaimForm, LoginForm, RegisterForm


def _login_limit() -> str:
    return current_app.config["LOGIN_RATELIMIT"]


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(_login_limit, methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        nickname = form.nickname.data.strip()
        player = Player.query.filter_by(nickname=nickname).first()

        if player is None or player.is_guest:
            flash("Neznáma prezývka.", "error")
        elif not player.is_claimed:
            # First login after migration → claim flow.
            return redirect(url_for("auth.claim", nickname=player.nickname))
        elif player.check_password(form.password.data):
            login_user(player)
            log_action("auth.login", entity=f"player:{player.id}")
            db.session.commit()
            next_url = request.args.get("next")
            return redirect(next_url if is_safe_url(next_url) else url_for("main.index"))
        else:
            flash("Nesprávne heslo.", "error")

    return render_template("auth/login.html", form=form)


@bp.route("/claim/<nickname>", methods=["GET", "POST"])
@limiter.limit(_login_limit, methods=["POST"])
def claim(nickname: str):
    player = Player.query.filter_by(nickname=nickname).first()
    if player is None or player.is_guest:
        flash("Neznáma prezývka.", "error")
        return redirect(url_for("auth.login"))
    if player.is_claimed:
        flash("Tento účet už má heslo. Prihlás sa — alebo požiadaj admina o reset.", "info")
        return redirect(url_for("auth.login"))

    form = ClaimForm()
    if form.validate_on_submit():
        player.set_password(form.password.data)
        log_action("auth.claim", entity=f"player:{player.id}")
        db.session.commit()
        login_user(player)
        flash(f"Heslo nastavené. Vitaj, {player.nickname}!", "success")
        return redirect(url_for("main.index"))

    return render_template("auth/claim.html", form=form, player=player)


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit(_login_limit, methods=["POST"])
def register():
    """Open registration. A nickname that exists as a GUEST record is upgraded to
    a full account, keeping its match history; a registered nickname is refused."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        nickname = form.nickname.data.strip()
        player = Player.query.filter_by(nickname=nickname).first()

        if player is not None and not player.is_guest:
            flash("Táto prezývka už existuje. Prihlás sa, alebo si vyber inú.", "error")
            return render_template("auth/register.html", form=form)

        if player is None:
            player = Player(nickname=nickname)
            db.session.add(player)
        else:  # guest upgrade — history stays attached
            player.is_guest = False
        player.name = (form.name.data or "").strip() or None
        player.surname = (form.surname.data or "").strip() or None
        player.set_password(form.password.data)
        db.session.flush()

        # Auto-enrol in dues for the current season (original registration parity).
        season, _ = seasons_svc.resolve()
        if season is not None and not Payment.query.filter_by(
            player_id=player.id, season_id=season.id
        ).first():
            db.session.add(Payment(player_id=player.id, season_id=season.id, status="Nevyplatené"))

        log_action("auth.register", entity=f"player:{player.nickname}")
        db.session.commit()
        login_user(player)
        flash(f"Vitaj, {player.nickname}! Registrácia hotová.", "success")
        return redirect(url_for("matches.calendar"))

    return render_template("auth/register.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    log_action("auth.logout", entity=f"player:{current_user.id}")
    db.session.commit()
    logout_user()
    flash("Odhlásený.", "info")
    return redirect(url_for("main.index"))


@bp.route("/reset/<int:player_id>", methods=["POST"])
@admin_required
def reset_password(player_id: int):
    """Admin resets a player's password → account returns to the unclaimed state
    and the player sets a new password on next login (D3)."""
    player = db.session.get(Player, player_id)
    if player is None or player.is_guest:
        flash("Hráč neexistuje.", "error")
        return redirect(url_for("main.index"))

    player.password_hash = None
    log_action("auth.password_reset", entity=f"player:{player.id}")
    db.session.commit()
    flash(f"Heslo pre {player.nickname} bolo zresetované — nastaví si nové pri prihlásení.", "success")
    return redirect(safe_referrer() or url_for("main.index"))

