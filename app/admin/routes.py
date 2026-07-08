"""Admin: dashboard, seasons & schedule generation, holidays, match management.

Everything here is @admin_required (closing audit #4's unprotected-route class).
Cancellation is a DB status flip — effective immediately on every page and worker
(closing NEW-3's stale in-memory cache).
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Holiday, Match, MatchStatus, Player, Season
from ..services import seasons as seasons_svc
from ..services import timing
from ..services.schedule import generate_schedule
from ..utils import admin_required, log_action, safe_referrer
from . import bp
from .forms import HolidayForm, SeasonForm


@bp.route("/")
@admin_required
def dashboard():
    season, off_season = seasons_svc.resolve()
    upcoming = None
    if season:
        now = timing.now_local()
        upcoming = (
            Match.query.filter_by(season_id=season.id, status=MatchStatus.scheduled)
            .order_by(Match.date)
            .all()
        )
        upcoming = next((m for m in upcoming if not timing.is_over(m.date, now)), None)

    unclaimed = Player.query.filter_by(is_guest=False, password_hash=None).count()
    return render_template(
        "admin/dashboard.html",
        season=season,
        off_season=off_season,
        upcoming=upcoming,
        unclaimed=unclaimed,
        players=Player.query.filter_by(is_guest=False).order_by(Player.nickname).all(),
    )


# ---- Seasons -------------------------------------------------------------------


@bp.route("/seasons", methods=["GET", "POST"])
@admin_required
def seasons():
    form = SeasonForm()
    if form.validate_on_submit():
        if Season.query.filter_by(label=form.label.data.strip()).first():
            flash("Sezóna s týmto označením už existuje.", "error")
        else:
            s = Season(
                label=form.label.data.strip(),
                starts_on=form.starts_on.data,
                ends_on=form.ends_on.data,
                match_weekday=int(form.match_weekday.data),
                match_start=form.match_start.data,
                match_end=form.match_end.data,
            )
            db.session.add(s)
            log_action("season.create", entity=f"season:{s.label}")
            db.session.commit()
            flash(f"Sezóna {s.label} vytvorená. Teraz môžeš vygenerovať zápasy.", "success")
            return redirect(url_for("admin.seasons"))

    season_rows = [
        (s, Match.query.filter_by(season_id=s.id).count())
        for s in seasons_svc.all_seasons()
    ]
    return render_template("admin/seasons.html", form=form, season_rows=season_rows)


@bp.route("/seasons/<int:season_id>/generate", methods=["POST"])
@admin_required
def generate(season_id: int):
    season = db.session.get(Season, season_id)
    if season is None:
        flash("Sezóna neexistuje.", "error")
        return redirect(url_for("admin.seasons"))

    report = generate_schedule(season)
    log_action(
        "season.generate_schedule",
        entity=f"season:{season.label}",
        payload={
            "created": len(report["created"]),
            "skipped_holiday": len(report["skipped_holiday"]),
            "skipped_existing": report["skipped_existing"],
        },
    )
    db.session.commit()

    skipped = ", ".join(
        f"{d.strftime('%d.%m.')} ({why})" for d, why in report["skipped_holiday"]
    )
    flash(
        f"Vygenerovaných {len(report['created'])} zápasov"
        f" · existujúcich preskočených: {report['skipped_existing']}"
        + (f" · sviatky/prázdniny: {skipped}" if skipped else ""),
        "success",
    )
    return redirect(url_for("admin.seasons"))


# ---- Holidays ----------------------------------------------------------------------


@bp.route("/holidays", methods=["GET", "POST"])
@admin_required
def holidays():
    form = HolidayForm()
    if form.validate_on_submit():
        h = Holiday(
            date_from=form.date_from.data,
            date_to=form.date_to.data,
            kind=form.kind.data,
            description=form.description.data or None,
        )
        db.session.add(h)
        log_action("holiday.create", entity=f"holiday:{h.date_from}..{h.date_to}")
        db.session.commit()
        flash("Voľno pridané.", "success")
        return redirect(url_for("admin.holidays"))

    rows = Holiday.query.order_by(Holiday.date_from.desc()).all()
    return render_template("admin/holidays.html", form=form, holidays=rows)


@bp.route("/holidays/<int:holiday_id>/delete", methods=["POST"])
@admin_required
def delete_holiday(holiday_id: int):
    h = db.session.get(Holiday, holiday_id)
    if h is not None:
        log_action("holiday.delete", entity=f"holiday:{h.date_from}..{h.date_to}")
        db.session.delete(h)
        db.session.commit()
        flash("Voľno odstránené.", "success")
    return redirect(url_for("admin.holidays"))


# ---- Matches (cancel / restore) --------------------------------------------------


@bp.route("/matches")
@admin_required
def matches():
    season, _ = seasons_svc.resolve(request.args.get("season"))
    rows = (
        Match.query.filter_by(season_id=season.id).order_by(Match.date.desc()).all()
        if season
        else []
    )
    return render_template(
        "admin/matches.html",
        season=season,
        seasons=seasons_svc.all_seasons(),
        matches=rows,
        now=timing.now_local(),
        is_over=timing.is_over,
    )


@bp.route("/matches/<int:match_id>/cancel", methods=["POST"])
@admin_required
def cancel_match(match_id: int):
    match = db.session.get(Match, match_id)
    if match is None:
        flash("Zápas neexistuje.", "error")
    elif match.status == MatchStatus.played or match.has_result:
        flash("Zápas s výsledkom sa nedá zrušiť.", "error")
    else:
        match.status = MatchStatus.cancelled
        log_action("match.cancel", entity=f"match:{match.date.isoformat()}")
        db.session.commit()
        flash(f"Zápas {match.date.strftime('%d.%m.%Y')} zrušený.", "success")
    return redirect(safe_referrer() or url_for("admin.matches"))


@bp.route("/matches/<int:match_id>/restore", methods=["POST"])
@admin_required
def restore_match(match_id: int):
    match = db.session.get(Match, match_id)
    if match is None:
        flash("Zápas neexistuje.", "error")
    elif match.status != MatchStatus.cancelled:
        flash("Zápas nie je zrušený.", "info")
    else:
        match.status = MatchStatus.scheduled
        log_action("match.restore", entity=f"match:{match.date.isoformat()}")
        db.session.commit()
        flash(f"Zápas {match.date.strftime('%d.%m.%Y')} obnovený.", "success")
    return redirect(safe_referrer() or url_for("admin.matches"))
