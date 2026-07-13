"""
record_saver.py
===============
Saves King's Trial game records in a custom 4-phase notation format.

Section 1 – HEADER: game metadata and result.
Section 2 – STATE:  full game state snapshot for load-state (JSON block).
Section 3 – MOVES:  4-phase move log, one cycle per row.

File extension: .kgt
"""

import os
import json
import datetime
from typing import Optional

# Save files are stored under a dedicated "saves" folder inside the project.
# This avoids confusion about the current working directory when running from
# different IDEs / launchers on Windows.
import sys
if getattr(sys, 'frozen', False):
    _PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    _PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
_SAVE_DIR = os.path.join(_PROJECT_ROOT, "saves")
# BUG-015 FIX: os.makedirs() is no longer called at import time (module-level side effect).
# The directory is created lazily inside save_game_record() on first save.
# This prevents import failures or unintended directory creation in web/server contexts.


def save_game_record(gs, result: str, config=None, path: str | None = None) -> str:
    """
    Write a complete game record to a .kgt file.

    Parameters
    ----------
    gs      : GameState — the finished (or paused) game state
    result  : str       — human-readable outcome
    config  : GameConfig|None — optional config to save
    path    : str | None — explicit path; auto-generated if None

    Returns
    -------
    str — path of the written file
    """
    # lazy import so the module is usable outside the game dir
    try:
        import constants as _c
        log = _c.log
    except ImportError:
        def log(msg: str) -> None:
            print(f"[KingsTrial] {msg}")

    # BUG-015: Create the saves directory here (lazily) rather than at import time.
    os.makedirs(_SAVE_DIR, exist_ok=True)

    if path is None:
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(_SAVE_DIR, f"KingsTrial_{ts}.kgt")
    else:
        # If user provided only a basenames (no directory), save it to our save folder.
        if os.path.basename(path) == path:
            path = os.path.join(_SAVE_DIR, path)

    # Ensure parent folder exists:
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # ── 1. Move log ───────────────────────────────────────────────────────
    records = list(gs.move_log)
    partial = dict(gs._current_log_entry)
    if any(partial.get(k) for k in ("w", "wn", "b", "bn")):
        partial.setdefault("cycle", gs.cycle)
        records.append(partial)

    # ── 2. State snapshot (JSON) ──────────────────────────────────────────
    board_list = [
        {"rank": sq[0], "col": sq[1], "type": p["type"], "owner": p["owner"]}
        for sq, p in gs.board.items()
    ]
    pool_w = [{"type": p["type"], "owner": p["owner"]} for p in gs.respawn_pool.get("white", [])]
    pool_b = [{"type": p["type"], "owner": p["owner"]} for p in gs.respawn_pool.get("black", [])]

    state_snapshot = {
        "phase":   gs.phase,
        "cycle":   gs.cycle,
        "points":  dict(gs.points),
        "timers":  {k: round(v, 3) for k, v in gs.timers.items()},
        "increment_sec": getattr(gs, "increment_sec", 5.0),
        "board":   board_list,
        "respawn_pool": {"white": pool_w, "black": pool_b},
        "king_respawn_queue": list(gs.king_respawn_queue),
        "game_over":   gs.game_over,
        "status_msg":  gs.status_msg,
    }
    
    if config:
        state_snapshot["config"] = vars(config)

    # ── 3. Assemble file ──────────────────────────────────────────────────
    sep  = "=" * 64
    dash = "-" * 63

    lines = [
        sep,
        "  KING'S TRIAL – GAME RECORD",
        f"  Date   : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  Cycles : {gs.cycle - 1}",
        f"  Result : {result}",
        f"  White  : {gs.points['white']} pts",
        f"  Black  : {gs.points['black']} pts",
        sep,
        "",
        "## STATE_SNAPSHOT_BEGIN",
        json.dumps(state_snapshot, separators=(",", ":")),
        "## STATE_SNAPSHOT_END",
        "",
        f"{'Cycle':<7} {'White':<14} {'W-Neutral':<14} {'Black':<14} {'B-Neutral':<14}",
        dash,
    ]

    for entry in records:
        cycle = entry.get("cycle", "?")
        w  = entry.get("w",  "—")
        wn = entry.get("wn", "—")
        b  = entry.get("b",  "—")
        bn = entry.get("bn", "—")
        lines.append(f"{str(cycle) + '.':<7} {w:<14} {wn:<14} {b:<14} {bn:<14}")

    lines += ["", sep]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log(f"record_saver: saved to '{path}'")
    return path


def _resolve_save_path(path: str) -> str:
    """Resolve a save file path, allowing bare filenames to resolve into the saves folder."""
    if os.path.isabs(path):
        return path

    # If the file exists relative to current working dir, use that.
    if os.path.exists(path):
        return os.path.abspath(path)

    # Otherwise, look inside the saves folder.
    candidate = os.path.join(_SAVE_DIR, path)
    return os.path.abspath(candidate)


def load_state_snapshot(path: str) -> Optional[dict]:
    """
    Parse the STATE_SNAPSHOT from a .kgt file.
    Returns the snapshot dict, or None if the file has no snapshot.
    """
    resolved = _resolve_save_path(path)
    try:
        with open(resolved, encoding="utf-8") as f:
            text = f.read()
        start = text.index("## STATE_SNAPSHOT_BEGIN\n") + len("## STATE_SNAPSHOT_BEGIN\n")
        end   = text.index("\n## STATE_SNAPSHOT_END", start)
        return json.loads(text[start:end])
    except (ValueError, KeyError, json.JSONDecodeError, FileNotFoundError):
        return None


def parse_move_log(path: str) -> list[dict]:
    """
    Parse the move log text table from a .kgt file.

    Returns a list of dicts:  { 'cycle': int, 'w': str, 'wn': str, 'b': str, 'bn': str }
    Empty strings are used for missing entries.

    The text table format (written by save_game_record) looks like:
        Cycle   White          W-Neutral      Black          B-Neutral
        ---------------------------------------------------------------
        1.      Pe4            Pd5            Pd5            Pe6
        2.      Ke2            ---            Kd19           Pe5
    """
    entries: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()

        # Find the section after STATE_SNAPSHOT_END
        after_snap = text.split("## STATE_SNAPSHOT_END", 1)[-1]

        # Find the dashes separator that marks the start of data rows
        lines = after_snap.splitlines()
        data_start = None
        for i, line in enumerate(lines):
            if line.startswith("---"):
                data_start = i + 1
                break

        if data_start is None:
            return []

        for line in lines[data_start:]:
            line = line.strip()
            if not line or line.startswith("="):
                break
            parts = line.split()
            if not parts:
                continue
            try:
                cycle_str = parts[0].rstrip(".")
                cycle = int(cycle_str)
            except ValueError:
                continue

            def _cell(i: int) -> str:
                v = parts[i] if i < len(parts) else ""
                return "" if v in ("—", "---", "-") else v

            entries.append({
                "cycle": cycle,
                "w":  _cell(1),
                "wn": _cell(2),
                "b":  _cell(3),
                "bn": _cell(4),
            })

    except Exception:
        pass

    return entries
