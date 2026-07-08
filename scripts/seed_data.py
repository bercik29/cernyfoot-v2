"""Static seed data carried over from the original app's hard-coded lists.

Sources: original flask_app.py (holidays, school_holidays) and statistics.py (SEASONS).
In v2 these live in the DB and become admin-editable; this module exists only to seed
them once during migration.
"""
from datetime import date

# (label, starts_on, ends_on) — original statistics.py L11-14
SEASONS = [
    ("2024/2025", date(2024, 9, 15), date(2025, 6, 30)),
    ("2025/2026", date(2025, 9, 18), date(2026, 6, 30)),
]

# Owner decision D1 — the canonical admin set.
ADMIN_NICKNAMES = {"berco", "frido", "michal", "tomasc"}

# Single-day public holidays — original flask_app.py L34-61
PUBLIC_HOLIDAYS = [
    (date(2024, 9, 15), "Sedembolestná Panna Mária"),
    (date(2024, 11, 1), "Sviatok všetkých svätých"),
    (date(2024, 11, 17), "Deň boja za slobodu a demokraciu"),
    (date(2024, 12, 24), "Štedrý deň"),
    (date(2024, 12, 25), "Prvý sviatok vianočný"),
    (date(2024, 12, 26), "Druhý sviatok vianočný"),
    (date(2025, 1, 1), "Nový rok"),
    (date(2025, 1, 6), "Zjavenie Pána"),
    (date(2025, 4, 18), "Veľký piatok"),
    (date(2025, 4, 21), "Veľkonočný pondelok"),
    (date(2025, 5, 1), "Sviatok práce"),
    (date(2025, 5, 8), "Deň víťazstva nad fašizmom"),
    (date(2025, 7, 5), "Sv. Cyril a Metod"),
    (date(2025, 9, 15), "Sedembolestná Panna Mária"),
    (date(2025, 11, 1), "Sviatok všetkých svätých"),
    (date(2025, 11, 17), "Deň boja za slobodu a demokraciu"),
    (date(2025, 12, 24), "Štedrý deň"),
    (date(2025, 12, 25), "Prvý sviatok vianočný"),
    (date(2025, 12, 26), "Druhý sviatok vianočný"),
    (date(2026, 1, 1), "Nový rok"),
    (date(2026, 1, 6), "Zjavenie Pána"),
    (date(2026, 4, 18), "Veľký piatok"),
    (date(2026, 4, 21), "Veľkonočný pondelok"),
    (date(2026, 5, 1), "Sviatok práce"),
    (date(2026, 5, 8), "Deň víťazstva nad fašizmom"),
    (date(2026, 7, 5), "Sv. Cyril a Metod"),
]

# (date_from, date_to, description) — original flask_app.py L64-73
SCHOOL_HOLIDAYS = [
    (date(2024, 10, 30), date(2024, 10, 31), "Jesenné prázdniny"),
    (date(2024, 12, 23), date(2025, 1, 7), "Vianočné prázdniny"),
    (date(2025, 2, 24), date(2025, 2, 28), "Jarné prázdniny"),
    (date(2025, 4, 17), date(2025, 4, 22), "Veľkonočné prázdniny"),
    (date(2025, 10, 30), date(2025, 10, 31), "Jesenné prázdniny"),
    (date(2025, 12, 22), date(2026, 1, 7), "Vianočné prázdniny"),
    (date(2026, 2, 16), date(2026, 2, 20), "Jarné prázdniny"),
    (date(2026, 4, 2), date(2026, 4, 7), "Veľkonočné prázdniny"),
]
