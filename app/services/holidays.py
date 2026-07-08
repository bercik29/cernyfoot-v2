"""Automatic Slovak holiday generation for a school year.

Public holidays are exact (fixed dates + Easter computed via the anonymous
Gregorian algorithm). School breaks follow the ministry's recurring pattern:

  * jesenné    — 30.–31.10. (stable in practice)
  * vianočné   — 22.12.–7.1.
  * veľkonočné — Thursday before Good Friday → Tuesday after Easter Monday
                 (matches the published 2025 and 2026 dates exactly)
  * jarné      — REGION-ROTATED by the ministry and announced per year; we seed
                 the week containing 20 February as a best guess and the admin
                 UI flags it for review.

Only day-offs that can collide with a match evening matter, so a one-day drift
on a break boundary is harmless unless it moves across a match weekday — the
generated rows are ordinary editable Holiday records either way.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..extensions import db
from ..models import Holiday


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian computus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


FIXED_PUBLIC = [
    ((1, 1), "Nový rok / Deň vzniku SR"),
    ((1, 6), "Zjavenie Pána"),
    ((5, 1), "Sviatok práce"),
    ((5, 8), "Deň víťazstva nad fašizmom"),
    ((7, 5), "Sv. Cyril a Metod"),
    ((8, 29), "Výročie SNP"),
    ((9, 15), "Sedembolestná Panna Mária"),
    ((11, 1), "Sviatok všetkých svätých"),
    ((11, 17), "Deň boja za slobodu a demokraciu"),
    ((12, 24), "Štedrý deň"),
    ((12, 25), "Prvý sviatok vianočný"),
    ((12, 26), "Druhý sviatok vianočný"),
]


def public_holidays(year: int) -> list:
    """(date, description) for one calendar year, Easter days included."""
    out = [(date(year, m, d), name) for (m, d), name in FIXED_PUBLIC]
    easter = easter_sunday(year)
    out.append((easter - timedelta(days=2), "Veľký piatok"))
    out.append((easter + timedelta(days=1), "Veľkonočný pondelok"))
    return sorted(out)


def _monday_of_week_containing(d: date) -> date:
    return d - timedelta(days=d.weekday())


def school_breaks(start_year: int) -> list:
    """(date_from, date_to, description) for school year start_year/start_year+1."""
    y2 = start_year + 1
    easter = easter_sunday(y2)
    good_friday = easter - timedelta(days=2)
    spring_monday = _monday_of_week_containing(date(y2, 2, 20))
    return [
        (date(start_year, 10, 30), date(start_year, 10, 31), "Jesenné prázdniny"),
        (date(start_year, 12, 22), date(y2, 1, 7), "Vianočné prázdniny"),
        (spring_monday, spring_monday + timedelta(days=4),
         "Jarné prázdniny (ODHAD — over podľa rozpisu ministerstva!)"),
        (good_friday - timedelta(days=1), easter + timedelta(days=2), "Veľkonočné prázdniny"),
    ]


def seed_school_year(start_year: int) -> dict:
    """Insert holidays for the school year (1.9.start_year – 31.8.start_year+1),
    skipping rows that already exist. Caller commits. Returns a report."""
    span_from, span_to = date(start_year, 9, 1), date(start_year + 1, 8, 31)
    existing = {
        (h.date_from, h.date_to, h.kind) for h in Holiday.query.all()
    }
    report = {"created": 0, "skipped": 0, "spring_estimate": None}

    def add(d_from: date, d_to: date, kind: str, desc: str) -> None:
        if (d_from, d_to, kind) in existing:
            report["skipped"] += 1
            return
        db.session.add(Holiday(date_from=d_from, date_to=d_to, kind=kind, description=desc))
        existing.add((d_from, d_to, kind))
        report["created"] += 1

    for d, name in public_holidays(start_year) + public_holidays(start_year + 1):
        if span_from <= d <= span_to:
            add(d, d, "public", name)

    for d_from, d_to, desc in school_breaks(start_year):
        add(d_from, d_to, "school", desc)
        if desc.startswith("Jarné"):
            report["spring_estimate"] = f"{d_from.strftime('%d.%m.')}–{d_to.strftime('%d.%m.%Y')}"

    return report
