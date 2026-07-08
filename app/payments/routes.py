"""Player-facing dues view. Marking payments is admin-only in v2 — the original
let any player mark themselves as paid (audit #12)."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..models import Payment, Season
from ..services import seasons as seasons_svc
from . import bp

PAID = "Vyplatené"
UNPAID = "Nevyplatené"


@bp.route("/payment")
@login_required
def my_payment():
    season, _ = seasons_svc.resolve(request.args.get("season"))
    if season is None:
        flash("Zatiaľ nie je vytvorená žiadna sezóna.", "info")
        return redirect(url_for("main.index"))

    current = Payment.query.filter_by(player_id=current_user.id, season_id=season.id).first()
    history = (
        Payment.query.filter_by(player_id=current_user.id)
        .join(Season)
        .order_by(Season.starts_on.desc())
        .all()
    )
    return render_template(
        "payments/my.html",
        season=season,
        seasons=seasons_svc.all_seasons(),
        status=current.status if current else UNPAID,
        history=history,
        PAID=PAID,
    )
