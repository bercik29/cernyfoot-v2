"""Admin: dashboard, seasons & schedule generation, holidays, match management,
team distribution, and result entry.

Everything here is @admin_required (closing audit #4's unprotected-route class).
Cancellation is a DB status flip — effective immediately on every page and worker
(closing NEW-3's stale in-memory cache).
"""
from __future__ import annotations

import random
import secrets

from flask import flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Holiday, Match, MatchStatus, Payment, Player, Season, Signup, Team
from ..services import form as form_svc
from ..services import seasons as seasons_svc
from ..services import timing
from ..services.balancing import balance_teams
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


# ---- Teams (distribute / manual / roster) ------------------------------------

def _managed_match(match_id: int) -> Match | None:
    match = db.session.get(Match, match_id)
    if match is None:
        flash("Zápas neexistuje.", "error")
    return match


@bp.route("/matches/<int:match_id>/distribute", methods=["POST"])
@admin_required
def distribute_teams(match_id: int):
    """Auto-balance the signed-up players into green/orange (ported algorithm).
    Every run is audit-logged with its seed and form scores, so a disputed split
    can be reproduced and explained (audit §5 recommendation)."""
    match = _managed_match(match_id)
    if match is None:
        return redirect(url_for("admin.matches"))
    if match.status == MatchStatus.cancelled or match.has_result:
        flash("Tímy sa nedajú rozdeliť — zápas je zrušený alebo už má výsledok.", "error")
    elif not match.signups:
        flash("Nikto nie je prihlásený.", "warning")
    else:
        scores = form_svc.form_scores_for(match.signups)
        seed = secrets.randbits(32)
        outcome = balance_teams(scores, random.Random(seed))
        green = set(outcome.green)
        for s in match.signups:
            s.team = Team.green if s.player.nickname in green else Team.orange
        log_action(
            "match.distribute",
            entity=f"match:{match.date.isoformat()}",
            payload={
                "seed": seed,
                "form_scores": scores,
                "green": outcome.green,
                "orange": outcome.orange,
            },
        )
        db.session.commit()
        flash(f"Tímy rozdelené ({len(outcome.green)} : {len(outcome.orange)}).", "success")
    return redirect(safe_referrer() or url_for("matches.detail", match_id=match_id))


@bp.route("/matches/<int:match_id>/teams", methods=["POST"])
@admin_required
def set_teams(match_id: int):
    """Manual team assignment: one select per signup (team_<signup_id>)."""
    match = _managed_match(match_id)
    if match is None:
        return redirect(url_for("admin.matches"))
    if match.status == MatchStatus.cancelled:
        flash("Zrušený zápas sa nedá upravovať.", "error")
        return redirect(safe_referrer() or url_for("matches.detail", match_id=match_id))

    valid = {t.value: t for t in Team}
    changed = 0
    for s in match.signups:
        raw = request.form.get(f"team_{s.id}")
        if raw in valid and s.team != valid[raw]:
            s.team = valid[raw]
            changed += 1
    if changed:
        log_action("match.set_teams", entity=f"match:{match.date.isoformat()}",
                   payload={"changed": changed})
        db.session.commit()
        flash("Tímy uložené.", "success")
    else:
        flash("Žiadna zmena.", "info")
    return redirect(safe_referrer() or url_for("matches.detail", match_id=match_id))


@bp.route("/matches/<int:match_id>/add_player", methods=["POST"])
@admin_required
def add_player(match_id: int):
    """Admin adds a player to the roster: an existing nickname joins as
    unassigned; an unknown nickname becomes a guest record. (The original's
    unauthenticated add_visiting_player — audit NEW-1/#4 — is gone.)"""
    match = _managed_match(match_id)
    if match is None:
        return redirect(url_for("admin.matches"))
    nickname = (request.form.get("nickname") or "").strip()
    if not nickname:
        flash("Zadaj prezývku.", "error")
    elif match.status == MatchStatus.cancelled:
        flash("Zrušený zápas sa nedá upravovať.", "error")
    else:
        player = Player.query.filter_by(nickname=nickname).first()
        if player is None:
            player = Player(nickname=nickname, is_guest=True)
            db.session.add(player)
            db.session.flush()
        if any(s.player_id == player.id for s in match.signups):
            flash(f"{nickname} už je na súpiske.", "info")
        else:
            team = Team.guest if player.is_guest else Team.unassigned
            db.session.add(Signup(match_id=match.id, player_id=player.id, team=team))
            log_action("match.add_player", entity=f"match:{match.date.isoformat()}",
                       payload={"player": nickname, "guest": player.is_guest})
            db.session.commit()
            flash(f"{nickname} pridaný na súpisku.", "success")
    return redirect(safe_referrer() or url_for("matches.detail", match_id=match_id))


@bp.route("/matches/<int:match_id>/remove_player/<int:player_id>", methods=["POST"])
@admin_required
def remove_player(match_id: int, player_id: int):
    match = _managed_match(match_id)
    if match is None:
        return redirect(url_for("admin.matches"))
    signup = Signup.query.filter_by(match_id=match_id, player_id=player_id).first()
    if signup is None:
        flash("Hráč nie je na súpiske.", "info")
    else:
        nickname = signup.player.nickname
        db.session.delete(signup)
        log_action("match.remove_player", entity=f"match:{match.date.isoformat()}",
                   payload={"player": nickname})
        db.session.commit()
        flash(f"{nickname} odstránený zo súpisky.", "success")
    return redirect(safe_referrer() or url_for("matches.detail", match_id=match_id))


# ---- Payments (admin matrix) ---------------------------------------------------

PAID, UNPAID = "Vyplatené", "Nevyplatené"


@bp.route("/payments", methods=["GET", "POST"])
@admin_required
def payments():
    season, _ = seasons_svc.resolve(request.args.get("season") or request.form.get("season"))
    if season is None:
        flash("Zatiaľ nie je vytvorená žiadna sezóna.", "info")
        return redirect(url_for("admin.dashboard"))

    players = Player.query.filter_by(is_guest=False).order_by(Player.nickname).all()

    # Auto-enrol: every registered player gets a row for the selected season.
    existing = {p.player_id: p for p in Payment.query.filter_by(season_id=season.id)}
    for player in players:
        if player.id not in existing:
            row = Payment(player_id=player.id, season_id=season.id, status=UNPAID)
            db.session.add(row)
            existing[player.id] = row
    db.session.flush()

    if request.method == "POST":
        changed = 0
        for player in players:
            status = request.form.get(f"status_{player.id}")
            if status in (PAID, UNPAID) and existing[player.id].status != status:
                existing[player.id].status = status
                changed += 1
        log_action("payments.update", entity=f"season:{season.label}",
                   payload={"changed": changed})
        db.session.commit()
        flash(f"Uložené ({changed} zmien).", "success")
        return redirect(url_for("admin.payments", season=season.label))

    db.session.commit()  # persist any auto-enrolled rows
    rows = [(p, existing[p.id]) for p in players]
    paid_count = sum(1 for _, pay in rows if pay.status == PAID)
    return render_template(
        "admin/payments.html",
        season=season,
        seasons=seasons_svc.all_seasons(),
        rows=rows,
        paid_count=paid_count,
        PAID=PAID,
        UNPAID=UNPAID,
    )


# ---- Result entry -------------------------------------------------------------------


@bp.route("/matches/<int:match_id>/result", methods=["POST"])
@admin_required
def set_result(match_id: int):
    """Enter/edit the final score. Allowed once the match is over (MATCH_LOCK);
    stores the score exactly once and flips the status to played."""
    match = _managed_match(match_id)
    if match is None:
        return redirect(url_for("admin.matches"))

    if match.status == MatchStatus.cancelled:
        flash("Zrušený zápas nemôže mať výsledok. Najprv ho obnov.", "error")
        return redirect(safe_referrer() or url_for("matches.detail", match_id=match_id))
    if not timing.is_over(match.date):
        flash("Výsledok sa dá zadať až po zápase.", "error")
        return redirect(safe_referrer() or url_for("matches.detail", match_id=match_id))

    try:
        green = int(request.form["green_score"])
        orange = int(request.form["orange_score"])
        if green < 0 or orange < 0:
            raise ValueError
    except (KeyError, ValueError):
        flash("Neplatné skóre.", "error")
        return redirect(safe_referrer() or url_for("matches.detail", match_id=match_id))

    match.green_score, match.orange_score = green, orange
    match.status = MatchStatus.played
    log_action("match.set_result", entity=f"match:{match.date.isoformat()}",
               payload={"score": f"{green}:{orange}"})
    db.session.commit()
    flash(f"Výsledok uložený: {green}:{orange}.", "success")
    return redirect(safe_referrer() or url_for("matches.detail", match_id=match_id))
