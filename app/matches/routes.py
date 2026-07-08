"""Calendar, match detail, sign-up/sign-out.

All timing checks go through services.timing — one deadline, one lock, everywhere.
"""
from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Match, MatchStatus, Signup, Team
from ..services import seasons, timing
from ..utils import log_action, safe_referrer
from . import bp


def _calendar_context(season, player):
    """Split a season's matches into past / upcoming / future for display."""
    now = timing.now_local()
    matches = (
        Match.query.filter_by(season_id=season.id).order_by(Match.date).all()
        if season
        else []
    )

    past, remaining = [], []
    for m in matches:
        (past if timing.is_over(m.date, now) else remaining).append(m)
    past.sort(key=lambda m: m.date, reverse=True)

    upcoming = next((m for m in remaining if m.status != MatchStatus.cancelled), None)
    future = [m for m in remaining if m is not upcoming]

    signed_up = False
    signup_count = 0
    if upcoming is not None:
        signup_count = len(upcoming.signups)
        if player is not None:
            signed_up = any(s.player_id == player.id for s in upcoming.signups)

    return {
        "past_matches": past,
        "upcoming": upcoming,
        "future_matches": future,
        "signup_count": signup_count,
        "signed_up": signed_up,
        "signup_open": upcoming is not None and timing.is_signup_open(upcoming, now),
        "signup_deadline": timing.signup_deadline(upcoming.date) if upcoming else None,
    }


@bp.route("/calendar")
def calendar():
    season, off_season = seasons.resolve(request.args.get("season"))
    if season is None:
        flash("Zatiaľ nie je vytvorená žiadna sezóna.", "info")
        return render_template(
            "matches/calendar.html", season=None, seasons=[], off_season=False,
            past_matches=[], upcoming=None, future_matches=[],
            signup_count=0, signed_up=False, signup_open=False, signup_deadline=None,
        )

    player = current_user if current_user.is_authenticated else None
    ctx = _calendar_context(season, player)
    return render_template(
        "matches/calendar.html",
        season=season,
        seasons=seasons.all_seasons(),
        off_season=off_season,
        **ctx,
    )


@bp.route("/match/<int:match_id>")
def detail(match_id: int):
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)

    by_team = {Team.green: [], Team.orange: [], Team.unassigned: [], Team.guest: []}
    for s in match.signups:
        by_team[s.team].append(s.player)

    signed_up = current_user.is_authenticated and any(
        s.player_id == current_user.id for s in match.signups
    )
    return render_template(
        "matches/detail.html",
        match=match,
        by_team=by_team,
        signed_up=signed_up,
        signup_open=timing.is_signup_open(match),
        signup_deadline=timing.signup_deadline(match.date),
        is_match_over=timing.is_over(match.date),
    )


@bp.route("/match/<int:match_id>/signup", methods=["POST"])
@login_required
def signup(match_id: int):
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)
    if not timing.is_signup_open(match):
        flash("Prihlasovanie na tento zápas je už uzavreté.", "error")
    elif any(s.player_id == current_user.id for s in match.signups):
        flash("Už si prihlásený.", "info")
    else:
        db.session.add(Signup(match_id=match.id, player_id=current_user.id, team=Team.unassigned))
        log_action("match.signup", entity=f"match:{match.id}")
        db.session.commit()
        flash(f"Prihlásený na {match.date.strftime('%d.%m.%Y')}. ⚽", "success")
    return redirect(safe_referrer() or url_for("matches.detail", match_id=match.id))


@bp.route("/match/<int:match_id>/signout", methods=["POST"])
@login_required
def signout(match_id: int):
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)
    if not timing.is_signup_open(match):
        flash("Odhlasovanie je už uzavreté.", "error")
    else:
        existing = Signup.query.filter_by(match_id=match.id, player_id=current_user.id).first()
        if existing is None:
            flash("Nie si prihlásený na tento zápas.", "info")
        else:
            db.session.delete(existing)
            log_action("match.signout", entity=f"match:{match.id}")
            db.session.commit()
            flash("Odhlásený zo zápasu.", "success")
    return redirect(safe_referrer() or url_for("matches.detail", match_id=match.id))
