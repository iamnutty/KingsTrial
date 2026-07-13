"""
ai/base_ai.py
=============
Abstract base for all AI implementations in King's Trial.

Each AI must implement `choose_move(gs) -> (from_sq, to_sq) | None`.
The scene asks the AI for a move choice, then executes it and animates it.
"""

from __future__ import annotations
from abc import ABC, abstractmethod


class BaseAI(ABC):
    """Abstract AI player.  Subclasses implement `choose_move`."""

    @abstractmethod
    def choose_move(
        self, gs: object
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """
        Return (from_sq, to_sq) for the AI's chosen move, or None if no
        legal moves exist.  Must not modify gs.
        """
        ...

    def name(self) -> str:
        """Human-readable name for UI display."""
        return self.__class__.__name__
