"""Single source of truth for match timing.

The original app hard-coded FIVE different cutoff times across routes (audit NEW-2:
18:45, 19:00, 19:05, 19:19, 19:55), so the same match was simultaneously "past" and
"upcoming" on different pages. In v2 there are exactly two configured moments:

  SIGNUP_DEADLINE — after this (on match day) sign-up/sign-out closes;
  MATCH_LOCK      — after this the match counts as played/over everywhere
                    (results, stats, calendar history).

All functions accept an optional `now` for testability.
"""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from flask import current_app

from ..models import Match, MatchStatus


def _parse_hhmm(value: str) -> time:
    h, m = value.strip().split(":")
    return time(int(h), int(m))


def tz() -> ZoneInfo:
    return ZoneInfo(current_app.config["TIMEZONE"])


def now_local() -> datetime:
    return datetime.now(tz())


def signup_deadline(match_date: date) -> datetime:
    return datetime.combine(
        match_date, _parse_hhmm(current_app.config["SIGNUP_DEADLINE"]), tzinfo=tz()
    )


def match_lock(match_date: date) -> datetime:
    return datetime.combine(
        match_date, _parse_hhmm(current_app.config["MATCH_LOCK"]), tzinfo=tz()
    )


def is_signup_open(match: Match, now: datetime | None = None) -> bool:
    """Sign-up/sign-out is possible only for scheduled matches before the deadline."""
    now = now or now_local()
    return match.status == MatchStatus.scheduled and now < signup_deadline(match.date)


def is_over(match_date: date, now: datetime | None = None) -> bool:
    """The match belongs to history (results/stats) once MATCH_LOCK has passed."""
    now = now or now_local()
    return now > match_lock(match_date)
