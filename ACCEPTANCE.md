# Acceptance Criteria — Evidence (audit §9)

All 10 criteria from the audit report, with where each is enforced. The whole suite:
`pytest` → **79 passed**.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Zero unauthenticated mutating endpoints (automated route-table test) | ✅ | `tests/test_security.py::test_no_unauthenticated_mutating_endpoints` walks the live route table; the only public POSTs are the explicit auth allowlist (`login`, `claim`, `register`) guarded by `test_all_post_endpoints_are_known` |
| 2 | All forms CSRF-protected; secret from env; argon2 passwords | ✅ | Global `CSRFProtect` + `test_csrf_enforced_when_enabled`; prod **refuses to boot** with the fallback key (`test_prod_refuses_default_secret`); `Player.set_password` uses argon2id (see any migrated claim: hash prefix `$argon2id$`) |
| 3 | Score stored exactly once per match; drift structurally impossible | ✅ | `matches.green_score/orange_score` are the only score columns; `signups` has no score field — the schema cannot express drift |
| 4 | ONE configurable signup deadline and match-lock | ✅ | `SIGNUP_DEADLINE` / `MATCH_LOCK` env values, consumed only via `app/services/timing.py`; boundary-tested in `tests/test_core_domain.py::test_deadline_and_lock_from_config` |
| 5 | New season creatable entirely from the admin UI | ✅ | `tests/test_core_domain.py::test_create_season_and_generate_from_ui` creates 2026/2027 + holidays + schedule via HTTP only |
| 6 | Migrated stats match the golden master (drift resolved per documented rule) | ✅ | `tests/test_stats_parity.py` — all 23 global + 12 personal metrics, both seasons, all 22 players, against `scripts/output/golden_master.json` (D2 drift rule, 2026-02-19 auto-cancel, whitespace-normalized nicknames — all documented in the migration report) |
| 7 | Balancing algorithm unit-tested; every auto-split logged with form scores | ✅ | `tests/test_teams_results.py` (determinism, completeness, 1000-draw balance properties); `admin.distribute_teams` writes seed + form scores + split to `audit_log` |
| 8 | Cancellation takes effect immediately, no app reload | ✅ | Status flip in DB, no caches; `tests/test_core_domain.py::test_cancel_effective_immediately` |
| 9 | Boots locally from a fresh clone with `.env` only | ✅ | No absolute paths anywhere (`grep -r "/home/bercik29" app/ scripts/` → only the migration's `--source` argument docs); this whole build ran on a Mac |
| 10 | Nightly automated backup verified restorable | ✅ | `scripts/backup_db.py` (online-backup API + `PRAGMA integrity_check` + retention), tested in `tests/test_backup.py`; PA task command in `DEPLOY.md` §8 |

## Resolved owner decisions (audit §10) — as implemented

- **D1** — admins seeded exactly `berco, frido, michal, tomasc` (`players.is_admin`).
- **D2** — drift resolved first-data-row-wins: `2025-01-23` → **8:11**, `2025-03-06` → **6:3**; reported in `scripts/output/migration_report.md`.
- **D3** — password claim flow, no strength rules, argon2 hashing, login rate limit (default 10/min/IP), admin reset returns account to unclaimed.

## Data fixes beyond the audit (documented in the migration report)

1. `2026-02-19` — past match with zero signups auto-cancelled (was inflating the
   original's played-match denominator).
2. `2025-02-06` — `"robert "` (trailing space) merged into `robert`; the original
   had a phantom 21st league row.
3. 12 unregistered nicknames preserved as guest records (upgradeable to full
   accounts by registering with that nickname).
