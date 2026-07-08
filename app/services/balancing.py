"""Team balancing — faithful port of the original algorithm (audit §5), made pure.

The original lived inside a view function, used the global `random`, and left no
trace of why a split came out the way it did. This port:
  * takes form scores in, returns the split — no I/O, no globals;
  * takes an explicit `random.Random`, so every split is reproducible from its seed;
  * returns the computed weights for logging.

Algorithm (unchanged from the original):
  1. rank players by form score (descending);
  2. assign draw weights symmetric around the middle: extremes get weight 1,
     the mid-table player gets ~0 — so the strongest and weakest tend to be
     drawn (and therefore placed) first;
  3. split the top half and bottom half separately: repeatedly weighted-draw a
     player and append them to whichever group currently has the lower total
     weight;
  4. cross-combine the four groups comparing total weights;
  5. coin-flip which combined group is green.

The odd-count centre double-write and the round-to-2-decimals draw-weight quirk
are preserved deliberately — this is the one piece of ported business logic and
its behaviour is the spec. The only change is a max(…, 0.01) crash-guard so a
weight that rounds to 0.00 can never produce an all-zero draw pool.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Mapping


@dataclass
class BalanceOutcome:
    green: list = field(default_factory=list)
    orange: list = field(default_factory=list)
    weights: dict = field(default_factory=dict)  # nickname -> normalized draw weight


def balance_teams(form_scores: Mapping[str, float], rng: random.Random) -> BalanceOutcome:
    sorted_players = sorted(form_scores.items(), key=lambda x: x[1], reverse=True)
    n = len(sorted_players)
    if n == 0:
        return BalanceOutcome()

    # Symmetric draw weights (original L511-521).
    weights = [0.0] * n
    midpoint = n // 2
    for i in range(midpoint + 1):
        w = 1 - (i / max(1, midpoint))
        weights[i] = w
        weights[-(i + 1)] = w
    total = sum(weights)
    normalized = [(2 * w) / total for w in weights] if total > 0 else [0.0] * n

    player_weights = {sorted_players[i][0]: normalized[i] for i in range(n)}
    players = list(player_weights.keys())

    def group_weight(group: list) -> float:
        return sum(player_weights[p] for p in group)

    def split_half(half: list) -> tuple[list, list]:
        """Weighted draw, appending to the currently lighter group (original L533-553)."""
        half = list(half)
        draw_weights = [player_weights[p] for p in half]
        g1: list = []
        g2: list = []
        while half:
            draw_weights = [max(round(w if w > 0 else 0.01, 2), 0.01) for w in draw_weights]
            pick = rng.choices(half, weights=draw_weights, k=1)[0]
            (g1 if group_weight(g1) <= group_weight(g2) else g2).append(pick)
            idx = half.index(pick)
            half.pop(idx)
            draw_weights.pop(idx)
        return g1, g2

    top_g1, top_g2 = split_half(players[:midpoint])
    bot_g1, bot_g2 = split_half(players[midpoint:])

    # Cross-combination (original L555-566).
    tw1, tw2 = group_weight(top_g1), group_weight(top_g2)
    bw1, bw2 = group_weight(bot_g1), group_weight(bot_g2)
    if tw1 >= tw2 and bw1 >= bw2:
        combined_1, combined_2 = top_g1 + bot_g1, top_g2 + bot_g2
    elif tw1 >= tw2:
        combined_1, combined_2 = top_g1 + bot_g2, top_g2 + bot_g1
    elif bw1 >= bw2:
        combined_1, combined_2 = top_g2 + bot_g1, top_g1 + bot_g2
    else:
        combined_1, combined_2 = top_g2 + bot_g2, top_g1 + bot_g1

    # Coin flip for colours (original L568-571).
    if rng.choice([True, False]):
        green, orange = combined_1, combined_2
    else:
        green, orange = combined_2, combined_1

    return BalanceOutcome(green=green, orange=orange, weights=player_weights)
