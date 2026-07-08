"""Schedule generation — an explicit admin action, not an import side-effect.

The original app rewrote matches.csv on every worker spawn (audit #8) and cached
cancellations in memory (NEW-3). Here an admin presses a button: weekly matches are
generated for a season on its configured weekday, skipping DB-stored holidays and
any date that already has a match (including cancelled ones — cancelling is final
unless explicitly restored).
"""
from __future__ import annotations

from datetime import date, timedelta

from ..extensions import db
from ..models import Holiday, Match, MatchStatus, Season


def generate_schedule(season: Season) -> dict:
    """Create missing matches for `season`. Returns a report dict. Caller commits."""
    holidays = Holiday.query.all()
    existing_dates = {m.date for m in Match.query.all()}  # match dates are globally unique

    def on_holiday(d: date) -> Holiday | None:
        for h in holidays:
            if h.date_from <= d <= h.date_to:
                return h
        return None

    report = {"created": [], "skipped_holiday": [], "skipped_existing": 0}

    d = season.starts_on + timedelta(days=(season.match_weekday - season.starts_on.weekday()) % 7)
    while d <= season.ends_on:
        h = on_holiday(d)
        if h is not None:
            report["skipped_holiday"].append((d, h.description or h.kind))
        elif d in existing_dates:
            report["skipped_existing"] += 1
        else:
            db.session.add(Match(season_id=season.id, date=d, status=MatchStatus.scheduled))
            report["created"].append(d)
        d += timedelta(days=7)

    return report
