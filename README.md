# Fodbal Černyševského — v2

A ground-up rebuild of the weekly-football sign-up & statistics app. Flask + SQLAlchemy
+ SQLite, real authentication, one configurable match deadline, DB-driven seasons and
admin rights. Replaces the original CSV-on-disk app (kept as a backup in `../cernyfoot`).

See `../cernyfoot/PROJECT_DESCRIPTION.md` and the audit report for background and the
binding decisions (D1 admins, D2 score-drift rule, D3 password auth).

## Local setup

```bash
cd cernyfoot-v2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit SECRET_KEY etc.

flask db upgrade              # create / migrate the SQLite database
flask run                     # http://127.0.0.1:5000
```

## Tests

```bash
pytest
```

## Project layout

```
cernyfoot-v2/
├── wsgi.py               # entry point (local dev + PythonAnywhere)
├── app/
│   ├── __init__.py       # create_app() factory
│   ├── config.py         # env-driven config (no hard-coded paths/secrets)
│   ├── extensions.py     # db, migrate, login_manager, csrf
│   ├── models.py         # full schema
│   ├── main/             # landing + health blueprint
│   ├── services/         # business logic (balancing, stats, schedule) — later phases
│   ├── templates/
│   └── static/
├── migrations/           # Alembic (via Flask-Migrate)
├── tests/
└── scripts/              # CSV→DB migration (Phase 1)
```

## Build status

- [x] **Phase 0 — Foundation**: app factory, config, schema, migrations, tests
- [x] **Phase 1 — CSV→DB migration**: `scripts/migrate_csv.py` (D1/D2 applied, reconciliation
      report in `scripts/output/`), golden master via `scripts/capture_golden_master.py`
- [x] **Phase 2 — Auth & authorization**: claim-flow password auth (D3), Flask-Login,
      CSRF on all forms, login rate limit, `admin_required`, admin password reset
- [x] **Phase 3 — Core domain**: single-deadline timing service, admin-driven schedule
      generator, calendar + signup/signout, cancellation with immediate effect,
      seasons & holidays admin UI
- [x] **Phase 4 — Teams & results**: ported balancing algorithm (pure, seeded, logged),
      manual team editor, roster add/remove, result entry (score stored once)
- [x] **Phase 5 — Statistics**: all 23 global + 12 personal metrics from one query per
      season; golden-master parity proven for both seasons (incl. the `robert ` phantom
      whitespace fix and the 2026-02-19 auto-cancel rule)
- [x] **Phase 6 — Frontend / UX**: payments (self-view + admin matrix), open registration
      with guest-history upgrade, players page, landing page, mobile bottom-nav,
      form-strip & league-bar charts
- [x] **Phase 7 — Cutover**: [DEPLOY.md](DEPLOY.md) runbook, verified nightly backup
      (`scripts/backup_db.py`), route-table security test, prod boot guard,
      [ACCEPTANCE.md](ACCEPTANCE.md) — all 10 audit criteria met

**Rebuild complete.** 79 tests · golden-master stats parity · all audit findings closed.
