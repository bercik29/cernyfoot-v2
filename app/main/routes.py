from flask import render_template

from ..models import Match, MatchStatus, Player
from ..services import seasons as seasons_svc
from ..services import timing
from . import bp


@bp.route("/")
def index():
    """Landing page with a glance at the next match."""
    upcoming = None
    signup_count = 0
    season, _ = seasons_svc.resolve()
    if season is not None:
        now = timing.now_local()
        for m in (
            Match.query.filter_by(season_id=season.id, status=MatchStatus.scheduled)
            .order_by(Match.date)
            .all()
        ):
            if not timing.is_over(m.date, now):
                upcoming = m
                signup_count = len(m.signups)
                break
    return render_template("index.html", upcoming=upcoming, signup_count=signup_count)


@bp.route("/players")
def players():
    rows = Player.query.filter_by(is_guest=False).order_by(Player.nickname).all()
    return render_template("players.html", players=rows)


@bp.route("/health")
def health():
    """Cheap liveness probe — also proves the app booted with its config."""
    return {"status": "ok"}
