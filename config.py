"""
config.py
=========
GameConfig dataclass — centralised settings for a King's Trial session.

Passed into scenes at construction so the future main menu can configure
AI strength, player colour, visual theme, and sound toggles without
touching game logic.
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field, asdict


# ---------------------------------------------------------------------------
# AI level presets (ELO targets used by Stockfish wrapper in Step 18)
# ---------------------------------------------------------------------------
AI_LEVELS = {
    "random":   None,       # RandomAI — no engine needed
    "easy":     1320,
    "medium":   1710,
    "hard":     2100,
}


@dataclass
class GameConfig:
    """All user-configurable settings for one game session."""

    # ── Player settings ────────────────────────────────────────────────────
    single_player: bool  = False          # True = human vs AI
    human_colour:  str   = "white"        # "white" | "black" | "random"

    # ── AI settings ────────────────────────────────────────────────────────
    neutral_ai:    str   = "random"       # key into AI_LEVELS
    opponent_ai:   str   = "random"       # key into AI_LEVELS (single-player)

    # ── Time Control ──────────────────────────────────────────────────────
    time_control:  str   = "5+10"         # key into TIME_CONTROLS in constants.py

    # ── Visual ────────────────────────────────────────────────────────────
    theme:         str   = "default"      # dynamic theme file pointer

    # ── Audio ─────────────────────────────────────────────────────────────
    sfx_volume:    int   = 2
    music_volume:  int   = 2

    # ── Layout file ───────────────────────────────────────────────────────
    layout_file:   str   = "TEST_CSV.csv"

    # ── Online / multiplayer ───────────────────────────────────────────────
    # relay_server_url is saved to config.json so the player can update it in
    # Settings if the server moves.  It defaults to localhost for local testing.
    # NOTE: theme, sfx_volume, and music_volume are deliberately NOT transmitted
    # during online sessions — each player always keeps their own visual/audio prefs.
    relay_server_url: str  = "ws://localhost:8765"
    relay_server_options: list[str] = field(default_factory=lambda: [
        "wss://kings-trial-server.fly.dev",
        "ws://localhost:8765"
    ])

    # Last room code used (host or join). Pre-fills the Join screen so players
    # can reconnect quickly after a disconnect or application restart.
    last_room_code: str = ""

    # ──────────────────────────────────────────────────────────────────────

    def _get_resolved_path(self, path: str) -> str:
        import sys
        if os.path.isabs(path):
            return path
        if getattr(sys, 'frozen', False):
            root = os.path.dirname(sys.executable)
        else:
            root = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(root, path)

    def save(self, path: str = "config.json") -> None:
        """Persist settings to a JSON file."""
        resolved = self._get_resolved_path(path)
        with open(resolved, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path: str = "config.json") -> "GameConfig":
        """Load settings from a JSON file, falling back to defaults."""
        import sys
        if os.path.isabs(path):
            resolved = path
        elif getattr(sys, 'frozen', False):
            resolved = os.path.join(os.path.dirname(sys.executable), path)
        else:
            resolved = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)

        if not os.path.exists(resolved):
            return cls()
        try:
            with open(resolved, encoding="utf-8") as f:
                data = json.load(f)

            # Handle legacy boolean sound settings gracefully
            if "sfx_enabled" in data:
                data["sfx_volume"] = 2 if data.pop("sfx_enabled") else 0
            if "music_enabled" in data:
                data["music_volume"] = 2 if data.pop("music_enabled") else 0

            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            # BUG-012 FIX: Narrowed from bare `except Exception` so unexpected errors
            # (PermissionError, MemoryError, etc.) are not silently swallowed.
            # We log the specific cause so the user/developer can diagnose and repair
            # a corrupted config file without wondering why settings keep resetting.
            import logging as _log
            _log.getLogger("KingsTrial.config").warning(
                "config.json could not be loaded (%s: %s). Using defaults.",
                type(exc).__name__, exc
            )
            return cls()
