"""
main.py
=======
King's Trial — entry point.

Creates the App (which owns the Pygame window and scene router) and
starts the main loop.  All game logic lives in scenes/ and game_state.py.

Run with (Linux/macOS):
    cd /path/to/KingsTrial
    ./venv/bin/python main.py

Run with (Windows PowerShell):
    cd C:\\path\\to\\KingsTrial
    .\\venv\\Scripts\\python.exe main.py
"""

import logging
from app import App
from config import GameConfig

# ── Logging setup ──────────────────────────────────────────────────────────
logging.basicConfig(
    level  = logging.DEBUG,
    format = "[KingsTrial] %(name)s: %(message)s",
)

# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    config = GameConfig.load()
    App(config).run()
