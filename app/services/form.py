"""Player form — points-per-game over recent matches, straight from SQL.

Replaces the original's per-player full-directory scan (~1,000 file opens per
distribute click, audit §5) with two indexed queries per player.

Rules (unchanged): Win = 3, Draw = 1, Loss = 0, over the last `n` played matches
across ALL seasons; a player with fewer than `min_games` total appearances gets
a form score of 0.0 so newcomers land in the mid-field of the ranking.
"""
from __future__ import annotations

from ..extensions import db
from ..models import Match, MatchStatus, Signup, Team

MIN_GAMES = 3
LAST_N = 10


def _played_rows(player_id: int):
    """(team, green_score, orange_score) for the player's played matches, newest first."""
    return (
        db.session.query(Signup.team, Match.green_score, Match.orange_score)
        .join(Match, Signup.match_id == Match.id)
        .filter(
            Signup.player_id == player_id,
            Match.status == MatchStatus.played,
            Signup.team.in_([Team.green, Team.orange]),
        )
        .order_by(Match.date.desc())
    )


def games_played(player_id: int) -> int:
    return _played_rows(player_id).count()


def form_score(player_id: int, n: int = LAST_N) -> float:
    rows = _played_rows(player_id).limit(n).all()
    if not rows:
        return 0.0
    points = 0
    for team, green, orange in rows:
        if green == orange:
            points += 1
        elif (team == Team.green and green > orange) or (team == Team.orange and orange > green):
            points += 3
    return points / len(rows)


def form_scores_for(signups) -> dict[str, float]:
    """Form score per signed-up player, applying the newcomer rule."""
    scores: dict[str, float] = {}
    for s in signups:
        if games_played(s.player_id) < MIN_GAMES:
            scores[s.player.nickname] = 0.0
        else:
            scores[s.player.nickname] = form_score(s.player_id)
    return scores
