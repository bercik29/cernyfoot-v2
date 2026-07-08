"""Season statistics — the original's 23 global + 12 personal metrics, computed
from ONE eager-loaded query per season instead of ~1,500 file opens (audit #13).

Semantics are a faithful port of the original statistics.py — including its
quirks, because the golden master is the spec:

  * every signup row counts in appearances/league table, including `Hosť` and
    `Unassigned` rows (guests collect losses on decided matches, draw points on
    draws — original all_players_stats behaviour);
  * "team side" for score contribution/differential is green for the green team
    and orange for EVERYONE ELSE (original `if row[1]=='Zelená' ... else orange`);
  * in the GLOBAL top-3 streaks, not playing breaks a streak; in the PERSONAL
    streaks it does not (two different original functions, both preserved);
  * ties in top-3 lists were non-deterministic in the original (set iteration);
    here they break deterministically by first appearance, and the parity tests
    compare tie-groups by value.

The dict keys returned by global_stats()/player_stats() match the golden master.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from itertools import combinations

from sqlalchemy.orm import joinedload

from ..models import Match, MatchStatus, Season, Signup, Team


@dataclass
class MatchStat:
    date: date
    green: int
    orange: int
    rows: list  # [(nickname, Team)] in original signup order


def _won(team: Team, g: int, o: int) -> bool:
    return (team == Team.green and g > o) or (team == Team.orange and o > g)


def _lost(team: Team, g: int, o: int) -> bool:
    return (team == Team.green and g < o) or (team == Team.orange and o < g)


def _side_score(team: Team, g: int, o: int) -> int:
    # Original: green team → green score, anyone else (incl. Hosť) → orange score.
    return g if team == Team.green else o


def _season_matches(season: Season, status: MatchStatus | None = None) -> list:
    q = Match.query.filter_by(season_id=season.id)
    if status is not None:
        q = q.filter_by(status=status)
    return q.options(joinedload(Match.signups).joinedload(Signup.player)).order_by(Match.date).all()


def played_matches(season: Season) -> list:
    """MatchStat per played match, chronological, rows in original signup order."""
    out = []
    for m in _season_matches(season, MatchStatus.played):
        if not m.has_result:
            continue
        rows = [(s.player.nickname, s.team) for s in sorted(m.signups, key=lambda s: s.id)]
        out.append(MatchStat(m.date, m.green_score, m.orange_score, rows))
    return out


# ---- Global statistics ---------------------------------------------------------


def global_stats(season: Season) -> dict:
    played = played_matches(season)
    cancelled_dates = [
        m.date.isoformat()
        for m in Match.query.filter_by(season_id=season.id, status=MatchStatus.cancelled)
        .order_by(Match.date)
    ]
    all_noncancelled = [
        m.date.isoformat()
        for m in Match.query.filter(
            Match.season_id == season.id, Match.status != MatchStatus.cancelled
        ).order_by(Match.date)
    ]

    n = len(played)
    total_goals = sum(m.green + m.orange for m in played)
    draw_count = sum(1 for m in played if m.green == m.orange)
    green_wins = sum(1 for m in played if m.green > m.orange)
    orange_wins = sum(1 for m in played if m.orange > m.green)

    # Appearances per player (row order = first-appearance order, deterministic).
    appearances: dict = defaultdict(int)
    wins: dict = defaultdict(int)
    losses: dict = defaultdict(int)
    matches_of: dict = defaultdict(int)
    for m in played:
        for nick, team in m.rows:
            appearances[nick] += 1
            matches_of[nick] += 1
            if _won(team, m.green, m.orange):
                wins[nick] += 1
            elif _lost(team, m.green, m.orange):
                losses[nick] += 1

    # Highest-scoring match (strictly greater → chronologically first max wins).
    best_total, best_date, best_score = 0, None, "0:0"
    for m in played:
        if m.green + m.orange > best_total:
            best_total = m.green + m.orange
            best_date, best_score = m.date.isoformat(), f"{m.green}:{m.orange}"

    # Most frequent 3-player same-team combos.
    combos: dict = defaultdict(int)
    for m in played:
        for team in (Team.green, Team.orange):
            members = sorted(nick for nick, t in m.rows if t == team)
            for combo in combinations(members, 3):
                combos[combo] += 1
    top_combo = sorted(combos.items(), key=lambda x: x[1], reverse=True)[:1]

    # League table (original all_players_stats semantics — every row counts).
    table: dict = {}
    for m in played:
        winner = Team.green if m.green > m.orange else (Team.orange if m.orange > m.green else None)
        for nick, team in m.rows:
            st = table.setdefault(
                nick, {"games_played": 0, "wins": 0, "draws": 0, "losses": 0, "points": 0}
            )
            st["games_played"] += 1
            if winner is not None and team == winner:
                st["wins"] += 1
                st["points"] += 3
            elif winner is None:
                st["draws"] += 1
                st["points"] += 1
            else:
                st["losses"] += 1
    table = dict(sorted(table.items(), key=lambda kv: kv[1]["points"], reverse=True))

    players_per_match = [len(m.rows) for m in played]
    count_freq: dict = defaultdict(int)
    for c in players_per_match:
        count_freq[c] += 1

    efficiency = {p: wins[p] / m for p, m in matches_of.items() if m > 0}

    def top3(d: dict, reverse=True):
        return sorted(d.items(), key=lambda kv: kv[1], reverse=reverse)[:3]

    return {
        "all_matches": all_noncancelled,
        "total_matches_played": (
            n,
            max((m.date for m in played), default=None).strftime("%d.%m.%Y") if played else None,
        ),
        "draws": (draw_count, draw_count / n if n else 0.0),
        "total_matches_cancelled": (len(cancelled_dates), sorted(cancelled_dates)),
        "total_goals_scored": total_goals,
        "average_goals_per_match": total_goals / n if n else 0,
        "most_frequent_players": sorted(appearances.items(), key=lambda kv: kv[1], reverse=True),
        "top_scoring_team": (
            "Remíza" if green_wins == orange_wins else ("Zelení" if green_wins > orange_wins else "Oranžoví"),
            green_wins,
            orange_wins,
            draw_count,
        ),
        "highest_scoring_match": (best_date, best_score),
        "most_frequent_team": top_combo,
        "top_3_highest_attendance": top3(appearances),
        "top_3_lowest_attendance": sorted(appearances.items(), key=lambda kv: kv[1])[:3],
        "top_3_most_wins": top3(wins),
        "top_3_most_losses": top3(losses),
        "top_3_longest_winning_streaks": _top3_streaks(played, want_wins=True),
        "top_3_longest_losing_streaks": _top3_streaks(played, want_wins=False),
        "average_players_per_match": sum(players_per_match) / n if n else 0,
        "most_frequent_number_of_players_per_match": (
            max(count_freq, key=count_freq.get) if count_freq else 0
        ),
        "highest_number_of_players_per_match": max(players_per_match, default=0),
        "lowest_number_of_players_per_match": min(players_per_match, default=0),
        "highest_efficiency": top3(efficiency),
        "all_players_stats": table,
    }


def _top3_streaks(played: list, want_wins: bool) -> list:
    """Global streaks: NOT playing breaks the streak (original top_3_* semantics)."""
    order: list = []
    seen = set()
    for m in played:
        for nick, _ in m.rows:
            if nick not in seen:
                seen.add(nick)
                order.append(nick)

    streaks = {p: {"cur": 0, "max": 0} for p in order}
    for m in played:
        outcome = {}
        for nick, team in m.rows:
            outcome[nick] = _won(team, m.green, m.orange) if want_wins else _lost(
                team, m.green, m.orange
            )
        for p, d in streaks.items():
            if p in outcome and outcome[p]:
                d["cur"] += 1
            else:
                d["max"] = max(d["max"], d["cur"])
                d["cur"] = 0
    for d in streaks.values():
        d["max"] = max(d["max"], d["cur"])

    top = sorted(streaks.items(), key=lambda kv: kv[1]["max"], reverse=True)[:3]
    return [(p, d["max"]) for p, d in top]


# ---- Personal statistics ----------------------------------------------------------


def player_stats(nickname: str, season: Season) -> dict:
    played = played_matches(season)
    n_total = len(played)

    mine = []  # (MatchStat, Team) for matches the player appeared in
    for m in played:
        for nick, team in m.rows:
            if nick == nickname:
                mine.append((m, team))
                break

    green_count = sum(1 for _, t in mine if t == Team.green)
    orange_count = sum(1 for _, t in mine if t == Team.orange)

    wins = losses = draws = 0
    total_contribution = 0
    goal_diff = 0
    green_played = green_wins = orange_played = orange_wins = 0
    best_score, best_date = -1, None

    # Personal streaks: absence does NOT break them (original winning_losing_streak).
    cur_w = max_w = cur_l = max_l = cur_nl = max_nl = 0

    for m, team in mine:
        g, o = m.green, m.orange
        side = _side_score(team, g, o)
        total_contribution += side
        goal_diff += side - (o if team == Team.green else g)

        if _won(team, g, o):
            wins += 1
            cur_w += 1
            cur_l = 0
            cur_nl += 1
        elif g == o:
            draws += 1
            cur_nl += 1
            cur_l = 0
            cur_w = 0
        else:
            losses += 1
            cur_l += 1
            cur_w = 0
            cur_nl = 0
        max_w, max_l, max_nl = max(max_w, cur_w), max(max_l, cur_l), max(max_nl, cur_nl)

        if side > best_score:
            best_score, best_date = side, m.date.isoformat()

        if team == Team.green:
            green_played += 1
            green_wins += 1 if g > o else 0
        elif team == Team.orange:
            orange_played += 1
            orange_wins += 1 if o > g else 0

    decided = wins + losses
    green_rate = green_wins / green_played if green_played else 0
    orange_rate = orange_wins / orange_played if orange_played else 0

    return {
        "total_matches_played": (
            n_total,
            max((m.date for m in played), default=None).strftime("%d.%m.%Y") if played else None,
        ),
        "matches_played": len(mine),
        "team_breakdown": (green_count, orange_count),
        "wins_losses": (wins, losses, (wins / decided) * 100 if decided else 0, draws),
        "average_team_score_contribution": total_contribution / len(mine) if mine else 0,
        "winning_losing_streak": (max_w, max_l, max_nl),
        "pl_highest_scoring_match": (best_date, best_score),
        "team_performance": (green_rate, orange_rate),
        "goal_differential": goal_diff,
        "match_attendance_rate": len(mine) / n_total if n_total else 0,
        "team_affinity": (green_count, orange_count),
        "overall_team_efficiency": (green_rate, orange_rate),
    }
