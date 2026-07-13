"""
game_state.py
=============
Central mutable game state for King's Trial.

This module owns ALL game state that changes during play:
  - The board (dict mapping (rank, col) -> piece dict)
  - Current phase & cycle count
  - Captured piece lists (per player)
  - Points (per player)
  - Move log (4-column)
  - Selection state (which square is selected, legal move targets)

game_state does NOT render anything. It exposes methods that main.py
calls to query and mutate state. Pure logic, no Pygame imports.
"""

from __future__ import annotations
import copy
from constants import (
    PHASE_WHITE, PHASE_WHITE_NEUTRAL, PHASE_BLACK,
    PHASE_ORDER, PHASE_NAMES, MAX_CYCLES,
    START_WHITE_KING, START_BLACK_KING, RESPAWN_WHITE_KING, RESPAWN_BLACK_KING,
    KING_CAPTURE_BONUS, PIECE_VALUES, log,
)


# ---------------------------------------------------------------------------
# Piece representation
# ---------------------------------------------------------------------------

def make_piece(ptype: str, owner: str) -> dict:
    """
    Create a piece dict.
    ptype: 'P','N','B','R','Q','K'
    owner: 'white','black','neutral'
    """
    return {"type": ptype, "owner": owner}


# ---------------------------------------------------------------------------
# GameState class
# ---------------------------------------------------------------------------

class GameState:
    """
    Encapsulates all mutable game state for King's Trial.

    Board representation:
        self.board : dict[(rank, col)] -> piece_dict  or  None if empty
        rank and col are both 1-indexed.

    Piece dict: { 'type': str, 'owner': str }

    Selection state (managed by main.py via provided helpers):
        self.selected_sq   : (rank, col) | None
        self.legal_targets : list[(rank, col)]
    """

    def __init__(self, initial_pieces: list[dict], time_control: str = "5+10") -> None:
        """
        Initialise the game state from a list of piece dicts
        (as returned by layout_reader.load_board_state).
        """
        # ── Board ─────────────────────────────────────────────────────────
        self.board: dict[tuple, dict | None] = {}
        for p in initial_pieces:
            key = (p["rank"], p["col"])
            self.board[key] = make_piece(p["type"], p["owner"])

        log(f"GameState: board initialised with {len(self.board)} pieces")

        # ── Turn tracking ─────────────────────────────────────────────────
        self.phase     : int = PHASE_WHITE   # current phase in the 4-phase cycle
        self.cycle     : int = 1             # full cycle count (max = MAX_CYCLES = 49)
        self.game_over : bool = False
        self.status_msg: str = ""            # displayed in the status bar on game end

        # ── Points, Timers, Respawn Pool ──────────────────────────────────
        from constants import TIME_CONTROLS
        tc = TIME_CONTROLS.get(time_control, {"start_sec": 300, "inc_sec": 10})
        
        self.points      = {"white": 0, "black": 0, "neutral": 0}
        self.timers      = {
            "white":   float(tc["start_sec"]),
            "black":   float(tc["start_sec"]),
            "neutral": float(tc["start_sec"])
        }
        self.increment_sec = float(tc["inc_sec"])
        # BUG-003 FIX: Removed duplicate assignment that existed above this line.
        # The annotated initialisation below is the single source of truth.

        # Dynamic Playable Bounds & King Spawn Logic (Step 21b)
        self.min_playable_rank = 4
        self.max_playable_rank = 23
        self.white_king_spawn  = (4, 5)
        self.black_king_spawn  = (23, 4)

        # ── Captured piece tracking (for score display & respawn logic) ───
        # Each entry: { 'type': str, 'owner': str }
        self.captured: dict[str, list] = {
            "white":   [],   # pieces captured FROM white
            "black":   [],   # pieces captured FROM black
            "neutral": [],   # pieces captured FROM neutral
        }

        # ── Pieces off-board (player pieces that were captured & await respawn) ─
        # Indexed by original owner. These are pieces eligible to be respawned
        # by spending points next to the king.
        self.respawn_pool: dict[str, list] = {
            "white": [],
            "black": [],
        }

        # ── Auto-respawn queue (for Kings) ────────────────────────────────
        # Format: { 'owner': str, 'remaining_phases': int }
        # King respawns on the start of the next phase owned by 'owner'
        self.king_respawn_queue: list[dict] = []

        # ── Move log ──────────────────────────────────────────────────────
        # Each entry: { 'cycle': int, 'w': str, 'wn': str, 'b': str, 'bn': str }
        self.move_log: list[dict] = []
        self._current_log_entry: dict = self._empty_log_entry()

        # ── Selection state ───────────────────────────────────────────────
        self.selected_sq    : tuple | None = None
        self.legal_targets  : list[tuple]  = []

    # ------------------------------------------------------------------
    # Timer helpers
    # ------------------------------------------------------------------

    def update_timers(self, dt_sec: float) -> bool:
        """
        Decrement the timer of the current phase owner.
        Returns True if a timeout occurred.
        """
        if self.game_over:
            return False

        owner = self.current_owner()
        self.timers[owner] = max(0.0, self.timers[owner] - dt_sec)

        if self.timers[owner] <= 0.0:
            return True
        return False

    def handle_timeout(self) -> None:
        """
        Penalty for timing out: -1 pt and skip turn.
        """
        from constants import CLOCK_TIMEOUT_PENALTY, log
        owner = self.current_owner()
        self.points[owner] += CLOCK_TIMEOUT_PENALTY
        log(f"TIMEOUT: {owner} gets {CLOCK_TIMEOUT_PENALTY} pts and skips turn")
        self.advance_phase()

    # ------------------------------------------------------------------
    # Board helpers
    # ------------------------------------------------------------------

    def get(self, rank: int, col: int) -> dict | None:
        """Return the piece at (rank, col) or None if empty."""
        return self.board.get((rank, col))

    def is_empty(self, rank: int, col: int) -> bool:
        return (rank, col) not in self.board

    def all_pieces(self) -> list[dict]:
        """
        Return a flat list of piece dicts suitable for renderer.draw_pieces().
        Each dict has: rank, col, type, owner.
        """
        result = []
        for (rank, col), piece in self.board.items():
            result.append({
                "rank":  rank,
                "col":   col,
                "type":  piece["type"],
                "owner": piece["owner"],
            })
        return result

    def find_king(self, owner: str) -> tuple | None:
        """Return (rank, col) of owner's king, or None if not on board."""
        for (rank, col), piece in self.board.items():
            if piece["owner"] == owner and piece["type"] == "K":
                return rank, col
        return None

    def get_piece_counts(self, owner: str) -> dict[str, int]:
        counts = {"P": 0, "N": 0, "B": 0, "R": 0, "Q": 0, "K": 0}
        for p in self.board.values():
            if p["owner"] == owner:
                counts[p["type"]] = counts.get(p["type"], 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Current player helper
    # ------------------------------------------------------------------

    def current_owner(self) -> str:
        """
        Return which owner moves in the current phase.
        Neutral phases → 'neutral'
        """
        if self.phase == PHASE_WHITE:
            return "white"
        elif self.phase == PHASE_BLACK:
            return "black"
        else:
            return "neutral"

    # ------------------------------------------------------------------
    # Move execution
    # ------------------------------------------------------------------

    def execute_move(self, from_sq: tuple, to_sq: tuple) -> str | None:
        """
        Move the piece at from_sq to to_sq.
        Handles:
          - Normal move
          - Capture (removes target piece, awards points)
          - King capture (awards 20 pts, triggers respawn protocol)

        Returns a notation string like 'Ke4' or 'Kxe4', or None on failure.
        Caller is responsible for ensuring the move is already validated.
        """
        from_rank, from_col = from_sq
        to_rank,   to_col   = to_sq

        piece = self.board.get(from_sq)
        if piece is None:
            log(f"execute_move: no piece at {from_sq}")
            return None

        target = self.board.get(to_sq)
        capture_str = ""

        if target is not None:
            # --- Capture ---
            capture_str = "x"
            captured_owner = target["owner"]
            value = PIECE_VALUES.get(target["type"], 1)

            # Award points to the capturing player's owner
            scorer = piece["owner"]
            if target["type"] == "K":
                # King capture — big bonus
                self.points[scorer] += KING_CAPTURE_BONUS
                log(f"execute_move: KING captured! {scorer} +{KING_CAPTURE_BONUS} pts")
                
                if scorer == "neutral" and captured_owner in ("white", "black"):
                    opponent = "black" if captured_owner == "white" else "white"
                    self.points[opponent] += 15
                    log(f"execute_move: Neutral captured {captured_owner} King! {opponent} +15 pts")
                    
                # King capture protocol handled separately
                self._handle_king_capture(captured_owner)
            else:
                self.points[scorer] += value
                log(f"execute_move: {scorer} captures {target['type']} +{value} pts")

            # Record captured piece
            self.captured[captured_owner].append(copy.copy(target))

            # Player pieces go to respawn pool (neutral pieces do not respawn)
            if captured_owner in ("white", "black"):
                self.respawn_pool[captured_owner].append(copy.copy(target))

        # Move piece on board
        # (physical move happens below, but we calculate notation first while the
        # board reflects the pre-move state for disambiguation check)

        # --- Disambiguation logic ---
        # If multiple pieces of the same type/owner can reach to_sq, we must disambiguate.
        from move_validator import get_legal_moves
        
        others = []
        for sq, p in self.board.items():
            if sq == from_sq: continue
            if p["owner"] == piece["owner"] and p["type"] == piece["type"]:
                # Could this other piece reach the same target?
                if to_sq in get_legal_moves(sq, self):
                    others.append(sq)
        
        disambig = ""
        if others:
            # Try file first
            other_files = [o[1] for o in others]
            if from_col not in other_files:
                disambig = "ABCDEFGH"[from_col - 1].lower()
            else:
                # Same file? Use rank
                other_ranks = [o[0] for o in others]
                if from_rank not in other_ranks:
                    disambig = str(from_rank)
                else:
                    # Both? Use both
                    disambig = "ABCDEFGH"[from_col - 1].lower() + str(from_rank)

        # Build notation string
        file_letter = "ABCDEFGH"[to_col - 1]
        notation = f"{piece['type']}{disambig}{file_letter}{to_rank}{capture_str}"

        # Physically move piece on board
        del self.board[from_sq]
        self.board[to_sq] = piece

        # --- Neutral Auto-Promotion ---
        if piece["owner"] == "neutral" and piece["type"] == "P":
            if to_rank == self.min_playable_rank or to_rank == self.max_playable_rank:
                piece["type"] = "Q"
                notation += "=Q"
                log(f"execute_move: Neutral Pawn auto-promoted to Queen at the edge of the board ({to_rank}, {to_col})")

        # +1 point for making a move
        self.points[piece["owner"]] += 1

        # Record in current log entry
        phase_key = {
            PHASE_WHITE:         "w",
            PHASE_WHITE_NEUTRAL: "wn",
            PHASE_BLACK:         "b",
        }[self.phase]
        self._current_log_entry[phase_key] = notation

        log(f"execute_move: {piece['owner']} {notation} (phase={PHASE_NAMES[self.phase]})")
        return notation

    def _handle_king_capture(self, captured_owner: str) -> None:
        """
        On king capture:
          1. Remove ALL active pieces belonging to captured_owner from board.
          2. Move them all to the respawn pool.
          3. King will auto-respawn at the designated square on next turn.
        Note: the captured king itself is handled by execute_move (board removal).
        """
        to_remove = [sq for sq, p in self.board.items() if p["owner"] == captured_owner]
        if captured_owner == "neutral":
            # Neutral pieces don't respawn, just remove everything permanently
            for sq in to_remove:
                p = self.board.pop(sq)
                log(f"_handle_king_capture: removed neutral {p['type']} permanently")
            return

        for sq in to_remove:
            piece = self.board.pop(sq)
            if piece["type"] != "K":
                # King itself was at to_sq and will be overwritten by the attacker;
                # only non-king pieces need to be added to the respawn pool here.
                self.respawn_pool[captured_owner].append(copy.copy(piece))
                log(f"_handle_king_capture: removed {captured_owner} {piece['type']} to respawn pool")
            else:
                # King captured → queue for auto-respawn at the start of their next turn.
                self.king_respawn_queue.append({
                    "owner": captured_owner,
                    "remaining_phases": 2 # Respawns at the start of their next move turn
                })
                log(f"_handle_king_capture: {captured_owner} King queued for auto-respawn")

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    def execute_promotion(self, sq: tuple, new_type: str) -> str | None:
        """
        Spend points to promote piece at sq to new_type.
        Returns notation string (e.g. 'PE22=Q') if successful, else None.
        Promotion cost = piece_value_of_new_type + 1.
        """
        from constants import (
            PROMOTION_COST, PHASE_WHITE, PHASE_WHITE_NEUTRAL, PHASE_BLACK, log
        )
        piece = self.board.get(sq)
        if piece is None or new_type == "K" or new_type == piece["type"]:
            return None

        cost = PROMOTION_COST.get(new_type, 99)
        owner = piece["owner"]

        if new_type in ("N", "B", "R", "Q"):
            current_count = self.get_piece_counts(owner).get(new_type, 0)
            from constants import log, MAX_PIECE_LIMITS
            if current_count >= MAX_PIECE_LIMITS.get(new_type, 99):
                log(f"execute_promotion: {owner} cannot promote to {new_type} - limit reached ({MAX_PIECE_LIMITS[new_type]})")
                return None

        if self.points[owner] < cost:
            log(f"execute_promotion: {owner} cannot afford {new_type} (cost={cost})")
            return None

        self.points[owner] -= cost
        old_type = piece["type"]
        piece["type"] = new_type

        # Build notation: [OldType][File][Rank]=[NewType]
        rank, col = sq
        file_letter = "ABCDEFGH"[col - 1]
        notation = f"{old_type}{file_letter}{rank}={new_type}"

        # Record in current log entry
        phase_key = {
            PHASE_WHITE:         "w",
            PHASE_WHITE_NEUTRAL: "wn",
            PHASE_BLACK:         "b",
        }[self.phase]
        self._current_log_entry[phase_key] = notation

        log(f"execute_promotion: {owner} {notation} (-{cost} pts)")
        return notation

    def execute_demotion(self, sq: tuple, new_type: str) -> str | None:
        """
        Demote the piece at sq to new_type (must be a lower-value type).
        Refund = PIECE_VALUES[old_type] - PIECE_VALUES[new_type]
        (the raw value difference — the upgrade fee is not returned).

        Rules:
          - Cannot demote to same type, King, or a type of >= value.
          - Cannot demote a Pawn (lowest).
          - Notation: [OldType][File][Rank]>[NewType]  e.g. QE5>R
        """
        from constants import (
            PIECE_VALUES, PHASE_WHITE, PHASE_WHITE_NEUTRAL, PHASE_BLACK, log
        )
        piece = self.board.get(sq)
        if piece is None:
            return None

        old_type = piece["type"]
        owner    = piece["owner"]

        if old_type == "K" or old_type == "P":
            log(f"execute_demotion: cannot demote {old_type}")
            return None

        if new_type == "K" or new_type == old_type:
            log(f"execute_demotion: invalid target {new_type}")
            return None

        old_val = PIECE_VALUES.get(old_type, 0)
        new_val = PIECE_VALUES.get(new_type, 0)
        if new_val >= old_val:
            log(f"execute_demotion: {new_type} is not lower than {old_type}")
            return None

        refund = old_val - new_val
        piece["type"] = new_type
        self.points[owner] += refund

        rank, col = sq
        file_letter = "ABCDEFGH"[col - 1]
        notation = f"{old_type}{file_letter}{rank}>{new_type}"

        phase_key = {
            PHASE_WHITE:         "w",
            PHASE_WHITE_NEUTRAL: "wn",
            PHASE_BLACK:         "b",
        }[self.phase]
        self._current_log_entry[phase_key] = notation

        log(f"execute_demotion: {owner} {notation} (+{refund} pts)")
        return notation

    def execute_respawn(self, piece_type: str, target_sq: tuple) -> str | None:
        """
        Spend points to respawn a piece of piece_type at target_sq.
        target_sq must be empty and adjacent to the king.
        Notation: +[Piece][Target] (e.g. +PE5)
        """
        from constants import PIECE_VALUES, log, PHASE_WHITE, PHASE_WHITE_NEUTRAL, PHASE_BLACK, MAX_PIECE_LIMITS
        owner = self.current_owner()
        
        if piece_type in ("N", "B", "R", "Q"):
            current_count = self.get_piece_counts(owner).get(piece_type, 0)
            if current_count >= MAX_PIECE_LIMITS.get(piece_type, 99):
                log(f"execute_respawn: {owner} cannot spawn {piece_type} - limit reached ({MAX_PIECE_LIMITS[piece_type]})")
                return None

        if owner not in self.respawn_pool:
            log(f"execute_respawn: {owner} cannot respawn pieces")
            return None
        cost = PIECE_VALUES.get(piece_type, 99)

        if self.points[owner] < cost:
            log(f"execute_respawn: {owner} cannot afford {piece_type} (cost={cost})")
            return None

        # Take piece from pool
        piece_to_respawn = None
        if piece_type == "P":
            # Pawns can be spawned infinitely
            piece_to_respawn = make_piece("P", owner)
        else:
            for p in self.respawn_pool[owner]:
                if p["type"] == piece_type:
                    piece_to_respawn = p
                    break

            if not piece_to_respawn:
                log(f"execute_respawn: {owner} has no {piece_type} in pool")
                return None

            self.respawn_pool[owner].remove(piece_to_respawn)
            
        self.points[owner] -= cost
        self.board[target_sq] = piece_to_respawn
        piece_to_respawn["rank"], piece_to_respawn["col"] = target_sq

        # Build notation: +[Type][File][Rank]
        rank, col = target_sq
        file_letter = "ABCDEFGH"[col - 1]
        notation = f"+{piece_type}{file_letter}{rank}"

        # Record in log
        phase_key = {
            PHASE_WHITE:         "w",
            PHASE_WHITE_NEUTRAL: "wn",
            PHASE_BLACK:         "b",
        }[self.phase]
        self._current_log_entry[phase_key] = notation

        log(f"execute_respawn: {owner} {notation} (-{cost} pts)")
        return notation

    # ------------------------------------------------------------------
    # Turn advancement
    # ------------------------------------------------------------------

    def advance_phase(self) -> None:
        """
        Move to the next phase in the 4-phase cycle.
        On completing a full cycle (BN → White), increment cycle counter
        and save the finished log entry.
        """
        # --- Timer Increment ---
        # Award increment to the owner of the phase that is now ending,
        # whether they moved or timed out.
        owner_finished = self.current_owner()
        from constants import PHASE_WHITE, PHASE_WHITE_NEUTRAL, PHASE_BLACK, PHASE_ORDER, PHASE_NAMES, MAX_CYCLES
        self.timers[owner_finished] += self.increment_sec

        current_idx = PHASE_ORDER.index(self.phase)
        next_idx    = (current_idx + 1) % len(PHASE_ORDER)
        self.phase  = PHASE_ORDER[next_idx]

        if self.phase == PHASE_WHITE:   # wrapped around → cycle complete
            self._current_log_entry["cycle"] = self.cycle
            self.move_log.append(self._current_log_entry)
            self.cycle += 1
            self._current_log_entry = self._empty_log_entry()
            log(f"advance_phase: cycle {self.cycle} begins")

            # Check move-count draw / win
            if self.cycle > MAX_CYCLES:
                self._resolve_game_end()
                
            # --- Apply Board Shrink ---
            # Every 15 cycles (up to 45), the board shrinks at the start of the next cycle
            if (self.cycle - 1) % 15 == 0 and (self.cycle - 1) <= 45:
                self._apply_board_shrink()

        # --- King Auto-Respawn Logic ---
        # Ensure King always respawns before the player's turn begins if it's missing.
        active = self.current_owner()
        if active in ("white", "black"):
            has_king = any(p["owner"] == active and p["type"] == "K" for p in self.board.values())
            if not has_king:
                self._do_king_respawn(active)

        # Reset selection
        self.selected_sq   = None
        self.legal_targets = []

        log(f"advance_phase: now {PHASE_NAMES[self.phase]}")

        # --- Skip Neutral Phases if no neutrals remain ---
        if self.phase == PHASE_WHITE_NEUTRAL:
            has_neutrals = any(p["owner"] == "neutral" for p in self.board.values())
            if not has_neutrals:
                log(f"advance_phase: skipping {PHASE_NAMES[self.phase]} (no neutral pieces left)")
                self.advance_phase()

    def _apply_board_shrink(self) -> None:
        if self.max_playable_rank - self.min_playable_rank + 1 <= 8:
            return

        from constants import log
        
        # Ranks becoming unplayable
        shrink_w = [self.min_playable_rank, self.min_playable_rank + 1]
        shrink_b = [self.max_playable_rank - 1, self.max_playable_rank]

        self.min_playable_rank += 2
        self.max_playable_rank -= 2

        wr, wc = self.white_king_spawn
        self.white_king_spawn = (wr + 2, wc)
        br, bc = self.black_king_spawn
        self.black_king_spawn = (br - 2, bc)

        unplayable_all = shrink_w + shrink_b
        to_remove = []
        for (r, c), piece in self.board.items():
            if r in unplayable_all:
                to_remove.append((r, c))

        for sq in to_remove:
            piece = self.board.pop(sq)
            owner = piece["owner"]
            if owner != "neutral":
                if piece["type"] != "K":
                    self.respawn_pool[owner].append(piece)
                else:
                    self.king_respawn_queue.append({
                        "owner": owner,
                        "remaining_phases": 2
                    })
            self.captured[owner].append(piece)
            log(f"_apply_board_shrink: Crushed {owner} {piece['type']} at {sq}")
        
        # Check for auto-promotion of neutral pawns on new edges
        for (r, c), piece in self.board.items():
            if piece["owner"] == "neutral" and piece["type"] == "P":
                if r == self.min_playable_rank or r == self.max_playable_rank:
                    piece["type"] = "Q"
                    log(f"_apply_board_shrink: Neutral Pawn auto-promoted to Queen at ({r}, {c}) due to board shrink")

        log(f"_apply_board_shrink: Board shrunk to {self.min_playable_rank}..{self.max_playable_rank}")

    def _do_king_respawn(self, owner: str) -> None:
        """Place king at designated square or adjacent if occupied."""
        from constants import log
        target = self.white_king_spawn if owner == "white" else self.black_king_spawn
        
        # If occupied, find adjacent
        if target in self.board:
            found = False
            r, c = target
            for dr in [-1,0,1]:
                for dc in [-1,0,1]:
                    adj = (r+dr, c+dc)
                    if 1 <= adj[1] <= 8 and self.min_playable_rank <= adj[0] <= self.max_playable_rank:
                        if adj not in self.board:
                            target = adj
                            found = True
                            break
                if found: break
            if not found:
                # Fallback: search a wider radius if the immediate 9 squares are completely jammed
                for search_r in range(r-2, r+3):
                    for search_c in range(1, 9):
                        if 1 <= search_c <= 8 and self.min_playable_rank <= search_r <= self.max_playable_rank:
                            if (search_r, search_c) not in self.board:
                                target = (search_r, search_c)
                                found = True
                                break
                    if found: break
        
        self.board[target] = make_piece('K', owner)
        log(f"_do_king_respawn: {owner} King respawned at {target}")
        # BUG-004 FIX: Removed duplicate neutral-phase-skip logic that was here.
        # The identical check already exists at the bottom of advance_phase()
        # (lines 589-593 in the original file) and runs after this method returns.
        # Having both active caused a double-call to advance_phase(), risking
        # an incorrect double-phase-skip in PHASE_WHITE_NEUTRAL.

    def _resolve_game_end(self) -> None:
        """Called when 49 cycles are complete. Determine winner by points."""
        self.game_over = True
        wp = self.points["white"]
        bp = self.points["black"]
        if wp > bp:
            self.status_msg = f"WHITE WINS! ({wp} vs {bp} pts)"
        elif bp > wp:
            self.status_msg = f"BLACK WINS! ({bp} vs {wp} pts)"
        else:
            self.status_msg = f"DRAW! ({wp} pts each)"
        log(f"Game over: {self.status_msg}")

    # ------------------------------------------------------------------
    # Win condition checks (called after each move)
    # ------------------------------------------------------------------

    def check_win_conditions(self) -> None:
        """
        Check board-position win conditions:
          - White king reaches max_playable_rank → White wins
          - Black king reaches min_playable_rank → Black wins
        """
        if self.game_over:
            return

        wk = self.find_king("white")
        if wk and wk[0] >= self.max_playable_rank:
            self.game_over = True
            self.status_msg = f"WHITE WINS! King reached rank {self.max_playable_rank}!"
            log(self.status_msg)
            return

        bk = self.find_king("black")
        if bk and bk[0] <= self.min_playable_rank:
            self.game_over = True
            self.status_msg = f"BLACK WINS! King reached rank {self.min_playable_rank}!"
            log(self.status_msg)

    # ------------------------------------------------------------------
    # King auto-respawn
    # ------------------------------------------------------------------

    # BUG-009 FIX: auto_respawn_king() removed — it was dead code (never called
    # anywhere in the codebase) and would have placed the king at the wrong
    # coordinates after a board shrink (it used hardcoded RESPAWN_WHITE/BLACK_KING
    # constants rather than the dynamic white_king_spawn/black_king_spawn fields
    # that shift as the board shrinks). King respawn is handled by _do_king_respawn().

    def get_move_history(self) -> list[dict]:
        """
        Return the full history of moves, including the current cycle
        which may not be complete yet.
        """
        return self.move_log + [self._current_log_entry]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _empty_log_entry(self) -> dict:
        return {"cycle": self.cycle, "w": "", "wn": "", "b": "", "bn": ""}

    def reset(self, initial_pieces: list[dict], time_control: str = "5+10") -> None:
        """Full reset — reinitialise with a fresh piece list and time control.

        BUG-008 FIX: The original implementation called self.__init__(initial_pieces)
        without forwarding time_control, silently reverting any custom time control
        to the default '5+10'. The time_control parameter is now forwarded correctly.
        Note: GameplayScene.reset() creates a fresh GameState directly and does not
        call this method, so this fix is primarily defensive for future use.
        """
        self.__init__(initial_pieces, time_control=time_control)

    def restore_from_snapshot(self, snap: dict) -> None:
        """
        Restore all game state from a snapshot dict (as saved in .kgt files).

        The snapshot format is:
          { "phase", "cycle", "points", "timers", "board",
            "respawn_pool", "king_respawn_queue", "game_over", "status_msg" }

        Any missing keys fall back to safe defaults so old save files
        (e.g. ones without king_respawn_queue) still load cleanly.
        """
        from constants import PHASE_NAMES, PHASE_WHITE
        log("restore_from_snapshot: loading state")

        # Board
        self.board = {}
        for entry in snap.get("board", []):
            sq = (entry["rank"], entry["col"])
            self.board[sq] = {"type": entry["type"], "owner": entry["owner"]}

        # Phase / cycle / result
        self.phase      = snap.get("phase", PHASE_WHITE)
        self.cycle      = snap.get("cycle", 1)
        self.game_over  = snap.get("game_over", False)
        self.status_msg = snap.get("status_msg", "")

        # Points
        saved_pts = snap.get("points", {})
        self.points = {
            "white":   saved_pts.get("white",   0),
            "black":   saved_pts.get("black",   0),
            "neutral": saved_pts.get("neutral", 0),
        }

        # Timers
        saved_tmr = snap.get("timers", {})
        self.timers = {
            "white":   float(saved_tmr.get("white",   300)),
            "black":   float(saved_tmr.get("black",   300)),
            "neutral": float(saved_tmr.get("neutral", 300)),
        }
        self.increment_sec = snap.get("increment_sec", 5.0)

        # Respawn pools
        pool = snap.get("respawn_pool", {})
        self.respawn_pool = {
            "white": [make_piece(p["type"], p["owner"]) for p in pool.get("white", [])],
            "black": [make_piece(p["type"], p["owner"]) for p in pool.get("black", [])],
        }

        # King respawn queue
        self.king_respawn_queue = [
            dict(entry) for entry in snap.get("king_respawn_queue", [])
        ]

        # Clear selection state (new session)
        self.selected_sq   = None
        self.legal_targets = []

        # Reset move log (history from the save is in the text section)
        self.move_log            = []
        self._current_log_entry  = self._empty_log_entry()

        log(f"restore_from_snapshot: {len(self.board)} pieces, "
            f"cycle={self.cycle}, phase={PHASE_NAMES[self.phase]}, "
            f"white={self.points['white']}pts, black={self.points['black']}pts")

    # ------------------------------------------------------------------

