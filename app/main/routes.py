from flask import render_template

from ..models import Match, MatchStatus, Player
from ..services import seasons as seasons_svc
from ..services import stats as stats_svc
from ..services import timing
from . import bp


@bp.route("/")
def index():
    """Landing page: wordmark hero, last-match scoreboard, head-to-head tension
    bar and season tiles (view-layer data only — one stats call per request)."""
    season, off_season = seasons_svc.resolve()
    upcoming = None
    signup_count = 0
    last_match = None
    s = None
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
        last_match = (
            Match.query.filter_by(season_id=season.id, status=MatchStatus.played)
            .order_by(Match.date.desc())
            .first()
        )
        s = stats_svc.global_stats(season)
    return render_template(
        "index.html",
        season=season,
        off_season=off_season,
        upcoming=upcoming,
        signup_count=signup_count,
        last_match=last_match,
        s=s,
    )


@bp.route("/players")
def players():
    rows = Player.query.filter_by(is_guest=False).order_by(Player.nickname).all()
    return render_template("players.html", players=rows)


@bp.route("/health")
def health():
    """Cheap liveness probe — also proves the app booted with its config."""
    return {"status": "ok"}
