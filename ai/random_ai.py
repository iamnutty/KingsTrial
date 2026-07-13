"""
ai/random_ai.py
===============
RandomAI — picks a uniformly random legal move for the current owner.
Extracted from game_state.py (get_random_ai_move / perform_ai_move).
"""

from __future__ import annotations
import random
from .base_ai import BaseAI


class RandomAI(BaseAI):
    """Selects a random legal move. Used for Neutral pieces by default."""

    def choose_move(
        self, gs: object
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        from move_validator import get_all_legal_moves   # lazy import avoids circular
        moves = get_all_legal_moves(gs)
        if not moves:
            return None
        return random.choice(moves)

    def name(self) -> str:
        return "Random AI"
