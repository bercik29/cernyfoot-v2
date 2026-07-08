"""CSV → DB migration for the original cernyfoot backup.

Implements the binding owner decisions from the audit (2026-07-08):
  D1 — canonical admins: berco, frido, michal, tomasc (seeded as players.is_admin).
  D2 — score drift: the score on the FIRST data row of a match file wins; every file
       where the rule fired is listed in the reconciliation report.

Plus the documented data-hygiene rules:
  * skip non-date files (the stray `19:00.csv`),
  * strip the phantom `nickname` header identity from users.csv,
  * import `Hosť` rows as guest players excluded from standings,
  * normalise CRLF/LF and stray whitespace,
  * matches present only in cancelled_matches.csv still get a Match row (cancelled).

Usage:
    .venv/bin/python -m scripts.migrate_csv --source ../cernyfoot/static [--report PATH]

The script is idempotent: it wipes and re-imports domain data on every run.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

from app.models import (
    AuditLog,
    Holiday,
    Match,
    MatchStatus,
    Payment,
    Player,
    Season,
    Signup,
    Team,
)
from .seed_data import ADMIN_NICKNAMES, PUBLIC_HOLIDAYS, SCHOOL_HOLIDAYS, SEASONS

DATE_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv$")
SCORE_RE = re.compile(r"^(\d+):(\d+)$")

TEAM_MAP = {
    "Zelená": Team.green,
    "Oranžová": Team.orange,
    "Hosť": Team.guest,
    "Unassigned": Team.unassigned,
}

# Payments in the source CSV have no season dimension; they describe the season
# that was active when the backup was taken.
PAYMENTS_SEASON_LABEL = "2025/2026"


def _read_csv(path: Path) -> list[list[str]]:
    """Read a CSV with newline/whitespace normalisation (handles mixed CRLF/LF)."""
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        return [[cell.strip() for cell in row] for row in csv.reader(f) if row]


def parse_score(raw: str) -> tuple[int, int] | None:
    m = SCORE_RE.match(raw.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def migrate(source: Path, session, today: date | None = None) -> dict:
    """Run the full migration inside an app context. Returns the report dict."""
    today = today or date.today()
    report: dict = {
        "source": str(source),
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "drift_resolutions": [],
        "warnings": [],
        "guests_created": [],
        "skipped_files": [],
        "counts": {},
    }

    # ---- 0. Wipe domain data (idempotent re-runs) -------------------------------
    for model in (AuditLog, Payment, Signup, Match, Holiday, Season, Player):
        session.query(model).delete()
    session.flush()

    # ---- 1. Seasons ---------------------------------------------------------------
    seasons: dict[str, Season] = {}
    for label, starts, ends in SEASONS:
        s = Season(label=label, starts_on=starts, ends_on=ends)
        session.add(s)
        seasons[label] = s
    session.flush()

    def season_for(d: date) -> Season | None:
        for s in seasons.values():
            if s.starts_on <= d <= s.ends_on:
                return s
        return None

    # ---- 2. Holidays ----------------------------------------------------------------
    for d, desc in PUBLIC_HOLIDAYS:
        session.add(Holiday(date_from=d, date_to=d, kind="public", description=desc))
    for d_from, d_to, desc in SCHOOL_HOLIDAYS:
        session.add(Holiday(date_from=d_from, date_to=d_to, kind="school", description=desc))

    # ---- 3. Players (users.csv) ---------------------------------------------------
    players: dict[str, Player] = {}
    for row in _read_csv(source / "users.csv"):
        if len(row) < 3:
            report["warnings"].append(f"users.csv: short row skipped: {row}")
            continue
        name, surname, nickname = row[0], row[1], row[2]
        if nickname == "nickname":  # phantom header identity (audit NEW-4)
            continue
        if not nickname:
            report["warnings"].append(f"users.csv: empty nickname skipped: {row}")
            continue
        if nickname in players:
            report["warnings"].append(f"users.csv: duplicate nickname skipped: {nickname}")
            continue
        p = Player(
            nickname=nickname,
            name=name or None,
            surname=surname or None,
            is_admin=nickname in ADMIN_NICKNAMES,
        )
        session.add(p)
        players[nickname] = p
    session.flush()

    missing_admins = ADMIN_NICKNAMES - set(players)
    if missing_admins:
        report["warnings"].append(f"D1 admins not found in users.csv: {sorted(missing_admins)}")

    def get_or_create_player(nickname: str) -> Player:
        if nickname not in players:
            p = Player(nickname=nickname, is_guest=True)
            session.add(p)
            session.flush()
            players[nickname] = p
            report["guests_created"].append(nickname)
        return players[nickname]

    # ---- 4. Cancelled dates ------------------------------------------------------
    cancelled_dates: set[str] = set()
    for row in _read_csv(source / "cancelled_matches.csv"):
        if row and row[0]:
            cancelled_dates.add(row[0])

    # ---- 5. Matches + signups from statistics/*.csv -------------------------------
    stats_dir = source / "statistics"
    match_dates: dict[str, Path | None] = {}
    for fname in sorted(os.listdir(stats_dir)):
        m = DATE_NAME_RE.match(fname)
        if not m:
            report["skipped_files"].append(fname)
            continue
        match_dates[m.group(1)] = stats_dir / fname

    # Union in cancelled dates and schedule dates that have no stats file.
    for d in cancelled_dates:
        match_dates.setdefault(d, None)
    schedule_path = source / "matches.csv"
    if schedule_path.exists():
        for row in _read_csv(schedule_path):
            if row and row[0]:
                match_dates.setdefault(row[0], None)

    n_played = n_cancelled = n_scheduled = n_signups = 0
    for date_str in sorted(match_dates):
        try:
            match_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            report["warnings"].append(f"unparseable match date skipped: {date_str}")
            continue
        season = season_for(match_date)
        if season is None:
            report["warnings"].append(f"match {date_str} outside all seasons — skipped")
            continue

        # Read player rows (if a stats file exists).
        rows: list[list[str]] = []
        path = match_dates[date_str]
        if path is not None:
            raw = _read_csv(path)
            if raw and raw[0] and raw[0][0] == "Player":
                raw = raw[1:]  # drop header
            rows = [r for r in raw if r and r[0]]

        # D2: the first data row's (non-empty) score is canonical; log drift.
        canonical_score = None
        if rows:
            scores_seen: list[str] = []
            for r in rows:
                if len(r) > 2 and r[2] and r[2] not in scores_seen:
                    scores_seen.append(r[2])
            if scores_seen:
                canonical_score = parse_score(scores_seen[0])
                if len(scores_seen) > 1:
                    report["drift_resolutions"].append(
                        {
                            "file": f"{date_str}.csv",
                            "scores_seen": scores_seen,
                            "canonical": scores_seen[0],
                        }
                    )

        # Status resolution.
        if date_str in cancelled_dates:
            status, score = MatchStatus.cancelled, None
            n_cancelled += 1
        elif match_date <= today and rows and canonical_score is not None:
            status, score = MatchStatus.played, canonical_score
            n_played += 1
            if canonical_score == (0, 0):
                report["warnings"].append(
                    f"match {date_str} imported as played 0:0 — verify (not in cancelled list)"
                )
        else:
            status, score = MatchStatus.scheduled, None
            n_scheduled += 1
            if match_date <= today and rows:
                report["warnings"].append(
                    f"past match {date_str} has players but no parseable score — imported as scheduled"
                )
            elif match_date <= today:
                # e.g. 2026-02-19: past, not cancelled, zero signups. The original
                # stats engine counted such matches as played (filename-date only);
                # v2 does not. Flag for owner review / golden-master exception.
                report["warnings"].append(
                    f"past match {date_str} has no players and no result — imported as "
                    f"scheduled (original stats counted it as played)"
                )

        match = Match(
            season_id=season.id,
            date=match_date,
            status=status,
            green_score=score[0] if score else None,
            orange_score=score[1] if score else None,
        )
        session.add(match)
        session.flush()

        # Signups.
        seen_players: set[str] = set()
        for r in rows:
            nickname = r[0]
            if nickname in seen_players:
                report["warnings"].append(f"{date_str}: duplicate signup for {nickname} skipped")
                continue
            seen_players.add(nickname)
            raw_team = r[1] if len(r) > 1 else ""
            team = TEAM_MAP.get(raw_team)
            if team is None:
                report["warnings"].append(
                    f"{date_str}: unknown team {raw_team!r} for {nickname} → unassigned"
                )
                team = Team.unassigned
            session.add(Signup(match_id=match.id, player_id=get_or_create_player(nickname).id, team=team))
            n_signups += 1

    # ---- 6. Payments (subscriptions.csv → active season) ---------------------------
    payments_season = seasons[PAYMENTS_SEASON_LABEL]
    paid_status: dict[str, str] = {}
    for row in _read_csv(source / "subscriptions.csv"):
        if len(row) >= 2 and row[0] and row[0] != "nickname":
            paid_status[row[0]] = row[1]

    n_payments = 0
    for nickname, player in players.items():
        if player.is_guest:
            continue
        status = paid_status.pop(nickname, None)
        if status is None:
            status = "Nevyplatené"
            report["warnings"].append(
                f"{nickname} missing from subscriptions.csv — defaulted to Nevyplatené"
            )
        session.add(Payment(player_id=player.id, season_id=payments_season.id, status=status))
        n_payments += 1
    for orphan in paid_status:
        report["warnings"].append(f"subscriptions.csv entry with no registered player: {orphan}")

    # ---- 7. Audit trail + counts ---------------------------------------------------
    session.add(AuditLog(action="migration.csv_import", entity="all", payload_json=None))
    session.flush()

    report["counts"] = {
        "players_registered": sum(1 for p in players.values() if not p.is_guest),
        "players_guest": sum(1 for p in players.values() if p.is_guest),
        "admins": sum(1 for p in players.values() if p.is_admin),
        "seasons": len(seasons),
        "holidays": len(PUBLIC_HOLIDAYS) + len(SCHOOL_HOLIDAYS),
        "matches_total": n_played + n_cancelled + n_scheduled,
        "matches_played": n_played,
        "matches_cancelled": n_cancelled,
        "matches_scheduled": n_scheduled,
        "signups": n_signups,
        "payments": n_payments,
    }
    return report


def format_report(report: dict) -> str:
    lines = [
        "# CSV → DB Migration — Reconciliation Report",
        "",
        f"- Source: `{report['source']}`",
        f"- Run at: {report['run_at']}",
        "",
        "## Counts",
        "",
    ]
    lines += [f"- **{k}**: {v}" for k, v in report["counts"].items()]

    lines += ["", "## Score-drift resolutions (rule D2: first data row wins)", ""]
    if report["drift_resolutions"]:
        for d in report["drift_resolutions"]:
            lines.append(
                f"- `{d['file']}`: scores seen {d['scores_seen']} → canonical **{d['canonical']}**"
            )
    else:
        lines.append("- none")

    lines += ["", "## Guest players created (excluded from standings)", ""]
    lines += [f"- {g}" for g in report["guests_created"]] or ["- none"]

    lines += ["", "## Skipped files", ""]
    lines += [f"- `{f}`" for f in report["skipped_files"]] or ["- none"]

    lines += ["", "## Warnings", ""]
    lines += [f"- {w}" for w in report["warnings"]] or ["- none"]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="path to the original static/ dir")
    parser.add_argument(
        "--report",
        default="scripts/output/migration_report.md",
        help="where to write the reconciliation report",
    )
    args = parser.parse_args()

    source = Path(args.source).resolve()
    if not (source / "users.csv").exists():
        print(f"error: {source} does not look like the original static/ dir", file=sys.stderr)
        return 1

    from app import create_app
    from app.extensions import db

    app = create_app(os.environ.get("FLASK_CONFIG", "dev"))
    with app.app_context():
        report = migrate(source, db.session)
        db.session.commit()

    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_report(report), encoding="utf-8")
    print(format_report(report))
    print(f"report written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
