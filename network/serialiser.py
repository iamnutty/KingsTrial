"""
network/serialiser.py
=====================
King's Trial — Message serialiser / deserialiser.

Converts game actions to JSON-ready dicts for the relay,
and applies incoming messages directly to a GameState.
"""

from __future__ import annotations
import logging

log = logging.getLogger("KingsTrial.serialiser")


# ---------------------------------------------------------------------------
# Message builders  (called by the local client before sending)
# ---------------------------------------------------------------------------

def msg_move(room: str, from_sq: tuple, to_sq: tuple) -> dict:
    return {
        "type": "move",
        "room": room,
        "from": list(from_sq),
        "to":   list(to_sq),
    }


def msg_promote(room: str, sq: tuple, new_type: str, action: str = "promote") -> dict:
    """
    action: "promote" (spend points, upgrade) | "demote" (refund, downgrade)
    """
    return {
        "type":     "promote",
        "room":     room,
        "sq":       list(sq),
        "new_type": new_type,
        "action":   action,
    }


def msg_respawn(room: str, piece_type: str, target_sq: tuple) -> dict:
    return {
        "type":       "respawn",
        "room":       room,
        "piece_type": piece_type,
        "target":     list(target_sq),
    }


def msg_phase_sync(room: str, gs) -> dict:
    """Lightweight integrity check sent after every move.
    Timers are always included so the Joiner can apply drift-correction.
    """
    piece_count = len(gs.board)
    return {
        "type":        "phase_sync",
        "room":        room,
        "cycle":       gs.cycle,
        "phase":       gs.phase,
        "piece_count": piece_count,
        # Host sends its authoritative timer values so the Joiner can self-correct
        # when drift exceeds the configured threshold.
        "timers": {k: round(v, 3) for k, v in gs.timers.items()},
    }


def msg_state_snapshot(room: str, gs) -> dict:
    """Full board snapshot — sent by Host after a Joiner reconnects."""
    board_list = [
        {"rank": sq[0], "col": sq[1], "type": p["type"], "owner": p["owner"]}
        for sq, p in gs.board.items()
    ]
    pool_w = [{"type": p["type"], "owner": p["owner"]}
              for p in gs.respawn_pool.get("white", [])]
    pool_b = [{"type": p["type"], "owner": p["owner"]}
              for p in gs.respawn_pool.get("black", [])]

    return {
        "type": "state_snapshot",
        "room": room,
        "snapshot": {
            "phase":              gs.phase,
            "cycle":              gs.cycle,
            "points":             dict(gs.points),
            "timers":             {k: round(v, 3) for k, v in gs.timers.items()},
            "increment_sec":      getattr(gs, "increment_sec", 5.0),
            "board":              board_list,
            "respawn_pool":       {"white": pool_w, "black": pool_b},
            "king_respawn_queue": list(gs.king_respawn_queue),
            "game_over":          gs.game_over,
            "status_msg":         gs.status_msg,
        },
    }


def msg_session_config(room: str, config) -> dict:
    """Host sends game settings alongside colour choice."""
    return {
        "type":           "session_config",
        "room":           room,
        "layout_file":    config.layout_file,
        "time_control":   config.time_control,
        "neutral_ai":     config.neutral_ai,
    }


def msg_color_choice(room: str, host_color: str, config) -> dict:
    """
    Host announces colour selection AND sends session config at the same time
    so the relay can cache it for start_game forwarding.
    """
    return {
        "type":       "color_choice",
        "room":       room,
        "host_color": host_color,
        "session_config": {
            "layout_file":  config.layout_file,
            "time_control": config.time_control,
            "neutral_ai":   config.neutral_ai,
        },
    }


def msg_player_ready(room: str, role: str, host_color: str) -> dict:
    """
    Sent by each player when they click the Ready button.
    host_color is included so the relay can embed it in start_game.
    """
    return {
        "type":       "player_ready",
        "room":       room,
        "role":       role,
        "host_color": host_color,
    }


def msg_forfeit(room: str, forfeiting_color: str) -> dict:
    """
    Sent when a player clicks FORFEIT (End Game in online mode).
    The relay forwards this to the other player who then awards themselves the win.
    """
    return {
        "type":            "forfeit",
        "room":            room,
        "forfeiting_color": forfeiting_color,
    }


# ---------------------------------------------------------------------------
# Message applicator  (called by the receiving client to update GameState)
# ---------------------------------------------------------------------------

def apply_message(msg: dict, gs) -> str | None:
    """
    Apply an incoming game message to gs.
    Returns a notation string if a move was made, else None.
    Does NOT call advance_phase() — callers must do that themselves.
    """
    mtype = msg.get("type")

    if mtype == "move":
        from_sq = tuple(msg["from"])
        to_sq   = tuple(msg["to"])
        notation = gs.execute_move(from_sq, to_sq)
        if notation:
            log.debug("apply_message: move %s→%s  notation=%s", from_sq, to_sq, notation)
        else:
            log.warning("apply_message: execute_move returned None for %s→%s", from_sq, to_sq)
        return notation

    elif mtype == "promote":
        sq       = tuple(msg["sq"])
        new_type = msg["new_type"]
        action   = msg.get("action", "promote")
        if action == "promote":
            notation = gs.execute_promotion(sq, new_type)
        else:
            notation = gs.execute_demotion(sq, new_type)
        if notation:
            log.debug("apply_message: %s %s→%s  notation=%s", action, sq, new_type, notation)
        return notation

    elif mtype == "respawn":
        piece_type = msg["piece_type"]
        target     = tuple(msg["target"])
        notation   = gs.execute_respawn(piece_type, target)
        if notation:
            log.debug("apply_message: respawn %s at %s  notation=%s", piece_type, target, notation)
        return notation

    elif mtype == "state_snapshot":
        snap = msg.get("snapshot", {})
        gs.restore_from_snapshot(snap)
        log.info("apply_message: state snapshot applied (%d pieces)", len(gs.board))
        return None

    else:
        log.debug("apply_message: unhandled type %s", mtype)
        return None


# ---------------------------------------------------------------------------
# Phase sync check
# ---------------------------------------------------------------------------

def check_phase_sync(msg: dict, gs) -> bool:
    """
    Returns True if the remote phase_sync matches local state.
    A mismatch means the boards have diverged.
    """
    if msg.get("type") != "phase_sync":
        return True
    return (
        msg.get("cycle") == gs.cycle
        and msg.get("phase") == gs.phase
        and msg.get("piece_count") == len(gs.board)
    )
