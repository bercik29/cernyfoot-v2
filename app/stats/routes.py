"""Global and personal statistics pages."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..services import seasons as seasons_svc
from ..services import stats as stats_svc
from . import bp


@bp.route("/stats")
def global_stats():
    season, off_season = seasons_svc.resolve(request.args.get("season"))
    if season is None:
        flash("Zatiaľ nie je vytvorená žiadna sezóna.", "info")
        return redirect(url_for("main.index"))
    data = stats_svc.global_stats(season)
    return render_template(
        "stats/global.html",
        season=season,
        seasons=seasons_svc.all_seasons(),
        off_season=off_season,
        s=data,
        total_expected=len(data["all_matches"]),
    )


@bp.route("/my_stats")
@login_required
def my_stats():
    season, off_season = seasons_svc.resolve(request.args.get("season"))
    if season is None:
        flash("Zatiaľ nie je vytvorená žiadna sezóna.", "info")
        return redirect(url_for("main.index"))
    data = stats_svc.player_stats(current_user.nickname, season)
    history = stats_svc.player_history(current_user.nickname, season)
    return render_template(
        "stats/my.html",
        season=season,
        seasons=seasons_svc.all_seasons(),
        off_season=off_season,
        p=data,
        history=history,
    )
