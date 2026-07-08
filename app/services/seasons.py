"""Season resolution — fixes audit NEW-9 (string-max fallback masking off-season)."""
from __future__ import annotations

from datetime import date

from ..models import Season


def resolve(label: str | None = None, today: date | None = None) -> tuple[Season | None, bool]:
    """Return (season, off_season).

    Explicit label wins. Otherwise the season containing `today`; if none contains
    it (summer break), fall back to the latest season BY DATE — not by string max —
    and flag off_season=True so the UI can say so.
    """
    if label:
        s = Season.query.filter_by(label=label).first()
        if s is not None:
            return s, False

    today = today or date.today()
    s = Season.query.filter(Season.starts_on <= today, Season.ends_on >= today).first()
    if s is not None:
        return s, False

    s = Season.query.order_by(Season.starts_on.desc()).first()
    return s, s is not None


def all_seasons() -> list[Season]:
    return Season.query.order_by(Season.starts_on.desc()).all()
