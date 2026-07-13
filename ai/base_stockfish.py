import os
import re
import random
import shutil
import subprocess
import time
import logging
from stockfish import Stockfish
from constants import PIECE_VALUES

log = logging.getLogger("KingsTrial.ai")

import sys
_STOCKFISH_CANDIDATES = [
    os.path.join(os.getcwd(), "stockfish.exe"),
    os.path.join(os.getcwd(), "stockfish", "stockfish.exe"),
    r"C:\Program Files\Stockfish\stockfish.exe",
    r"C:\Program Files (x86)\Stockfish\stockfish.exe",
    r"C:\stockfish\stockfish.exe",
    "/usr/games/stockfish",
    "/usr/bin/stockfish",
    "/usr/local/bin/stockfish",
]

if getattr(sys, 'frozen', False):
    # If running in a PyInstaller bundle
    _exe_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    _sf_name = "stockfish" if os.name != "nt" else "stockfish.exe"
    _STOCKFISH_CANDIDATES.insert(0, os.path.join(_exe_dir, _sf_name))
    _STOCKFISH_CANDIDATES.insert(1, os.path.join(_exe_dir, "stockfish", _sf_name))

def _is_stockfish_executable(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    try:
        kwargs = {"capture_output": True, "text": True, "timeout": 5}
        if os.name == 'nt':
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run([path, "--version"], **kwargs)
        return result.returncode == 0
    except Exception:
        return False


def _make_stockfish_engine(path: str, depth: int) -> "Stockfish":
    """Construct a Stockfish instance that never opens a visible console window.

    The stockfish Python library spawns stockfish.exe via subprocess.Popen.
    On Windows, unless CREATE_NO_WINDOW is passed the process gets its own
    console window which flashes visibly.  The library exposes no direct
    kwarg for this, but it does forward arbitrary keyword arguments from
    ``parameters`` straight into its internal Popen call via the
    ``_put_file_name_in_path`` / ``_put_stockfish_go_depth_in_path`` chain.
    The cleanest supported hook is to temporarily monkey-patch Popen in a
    controlled, exception-safe way inside this single function so that ALL
    callers (initial start, crash-restart, engine reinit) go through one
    code path.
    """
    _original_popen = subprocess.Popen

    def _silent_popen(*args, **kwargs):
        if os.name == 'nt' and 'creationflags' not in kwargs:
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        return _original_popen(*args, **kwargs)

    subprocess.Popen = _silent_popen
    try:
        engine = Stockfish(path=path, depth=depth)
    finally:
        subprocess.Popen = _original_popen

    return engine


_FEN_RE = re.compile(
    r"^\s*(((?:[rnbqkpRNBQKP1-8]+\/){7})[rnbqkpRNBQKP1-8]+)"
    r"\s([bw])\s(-|[KQkq]{1,4})\s(-|[a-h][1-8])\s(\d+)\s(\d+)\s*$"
)
_PIECE_CHARS = frozenset("PNBRQKpnbrqk")


def _is_fen_syntax_valid(fen: str) -> bool:
    """Lightweight FEN syntax check — no subprocess spawned.

    Replaces engine.is_fen_valid() which internally creates a new Stockfish
    subprocess (without CREATE_NO_WINDOW) on every call, causing visible
    console windows to flash on Windows during every AI turn.

    This check mirrors the static portion of the stockfish library's own
    _is_fen_syntax_valid() but skips the live-engine move-legality probe
    that is the subprocess source.  Our FENs are machine-generated and
    structurally valid, so the syntax check is sufficient.
    """
    if not _FEN_RE.match(fen):
        return False
    board_part = fen.strip().split()[0]
    rows = board_part.split("/")
    if len(rows) != 8:
        return False
    has_white_king = False
    has_black_king = False
    for row in rows:
        col_count = 0
        prev_digit = False
        for ch in row:
            if ch.isdigit():
                if prev_digit:
                    return False  # two consecutive digits
                col_count += int(ch)
                prev_digit = True
            elif ch in _PIECE_CHARS:
                col_count += 1
                prev_digit = False
                if ch == 'K':
                    has_white_king = True
                elif ch == 'k':
                    has_black_king = True
            else:
                return False
        if col_count != 8:
            return False
    return has_white_king and has_black_king


def install_stockfish_engine() -> str:
    env_path = os.environ.get("STOCKFISH_PATH")
    if env_path:
        log.debug(f"Checking STOCKFISH_PATH: {env_path}")
        if _is_stockfish_executable(env_path):
            log.info(f"Stockfish binary found at: {env_path}")
            return env_path
        log.warning("STOCKFISH_PATH is set but not usable: %s", env_path)

    for exe in ("stockfish", "stockfish.exe"):
        path = shutil.which(exe)
        if path:
            log.debug(f"Checking PATH: {path}")
            if _is_stockfish_executable(path):
                log.info(f"Stockfish binary found at: {path}")
                return path

    for candidate in _STOCKFISH_CANDIDATES:
        log.debug(f"Checking candidate: {candidate}")
        if os.path.isfile(candidate):
            if candidate.startswith(os.getcwd()) or _is_stockfish_executable(candidate):
                log.info(f"Stockfish binary found at: {candidate}")
                return candidate

    raise FileNotFoundError("Stockfish binary not found. Install Stockfish or set STOCKFISH_PATH to its executable.")

class BaseStockfishAI:
    def __init__(self, elo: int = 2000, depth: int = 15, difficulty: str = "hard"):
        self.engine = None
        self.available = False
        self.difficulty = difficulty
        # BUG-013 FIX: Store depth explicitly rather than relying on engine._depth,
        # which is a private attribute of the stockfish library and not part of its
        # public API. Using it could break silently on any library upgrade.
        self._engine_depth: int = depth

        if self.difficulty == "random":
            log.info("AI Difficulty set to 'random'. Bypassing Stockfish engine initialization.")
            return

        try:
            stockfish_path = install_stockfish_engine()
            self.engine = _make_stockfish_engine(stockfish_path, depth)
            self.engine.set_elo_rating(elo)
            self.available = True
        except Exception as e:
            log.warning("Stockfish not available (%s). Falling back to random move selection.", e)

    def quit(self) -> None:
        """Properly close the underlying Stockfish engine subprocess to avoid background zombie processes."""
        if self.engine:
            try:
                self.engine.__del__()
            except Exception:
                pass
            self.engine = None
            self.available = False

    def _get_fallback_move(self, gs):
        from move_validator import get_all_legal_moves
        moves = get_all_legal_moves(gs)
        if not moves:
            return None
        return random.choice(moves)

    def _generate_attacked_squares(self, gs, ai_owners: tuple[str, ...]) -> set[tuple[int, int]]:
        from move_validator import get_legal_moves
        attacked = set()
        for from_sq, piece in gs.board.items():
            if piece["owner"] not in ai_owners:
                attacked.update(get_legal_moves(from_sq, gs, ignore_turn=True))
                
        # Danger squares from imminent shrink are inherently "attacked"
        cycles_until_shrink = 15 - ((gs.cycle - 1) % 15)
        if cycles_until_shrink <= 2 and gs.cycle <= 45:
            danger_ranks = [gs.min_playable_rank, gs.min_playable_rank + 1, gs.max_playable_rank - 1, gs.max_playable_rank]
            for r in danger_ranks:
                for c in range(1, 9):
                    attacked.add((r, c))
                    
        return attacked

    def _is_square_safe(self, sq: tuple[int, int], gs, active_color: str, ai_owners: tuple[str, ...], use_cache: bool = True) -> bool:
        """
        Check if square is safe from immediate capture by an enemy piece.
        Used for injecting check-free Dummy Kings.
        """
        if use_cache and hasattr(self, 'current_attacked_squares') and self.current_attacked_squares is not None:
            return sq not in self.current_attacked_squares
            
        # Add Danger Rank check when bypassing cache
        cycles_until_shrink = 15 - ((gs.cycle - 1) % 15)
        if cycles_until_shrink <= 2 and gs.cycle <= 45:
            danger_ranks = (gs.min_playable_rank, gs.min_playable_rank + 1, gs.max_playable_rank - 1, gs.max_playable_rank)
            if sq[0] in danger_ranks:
                return False
                
        r, c = sq
        enemy_owners = tuple(o for o in ["white", "black", "neutral"] if o not in ai_owners)
        
        # 1. Knights
        for dr, dc in [(2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)]:
            p = gs.board.get((r + dr, c + dc))
            if p and p["owner"] in enemy_owners and p["type"] == "N": return False
                
        # 2. Kings
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0: continue
                p = gs.board.get((r + dr, c + dc))
                if p and p["owner"] in enemy_owners and p["type"] == "K": return False
                    
        # 3. Sliders (Rook, Bishop, Queen)
        dirs = [
            (1, 0, ("R", "Q")), (-1, 0, ("R", "Q")),
            (0, 1, ("R", "Q")), (0, -1, ("R", "Q")),
            (1, 1, ("B", "Q")), (1, -1, ("B", "Q")),
            (-1, 1, ("B", "Q")), (-1, -1, ("B", "Q"))
        ]
        for dr, dc, attacker_types in dirs:
            for dist in range(1, 8):
                tr, tc = r + dr * dist, c + dc * dist
                if not (gs.min_playable_rank <= tr <= gs.max_playable_rank and 1 <= tc <= 8): break
                p = gs.board.get((tr, tc))
                if p:
                    if p["owner"] in enemy_owners and p["type"] in attacker_types: return False
                    break
                    
        # 4. Pawns
        for owner in enemy_owners:
            drs = [-1] if owner == "white" else ([1] if owner == "black" else [-1, 1])
            for dr in drs:
                for dc in [-1, 1]:
                    p = gs.board.get((r + dr, c + dc))
                    if p and p["owner"] == owner and p["type"] == "P": return False
                    
        return True

    def _find_safe_dummy_king_square(self, gs, rank_lo: int, rank_hi: int, active_color: str, ai_owners: tuple[str, ...], want_bottom: bool) -> tuple[int, int] | None:
        """
        Find a safe square for a Dummy King in the given 8-rank window.
        want_bottom=True  -> search from rank_lo up (Bottom corners preferred)
        want_bottom=False -> search from rank_hi down (Top corners preferred)
        """
        ranks = range(rank_lo, rank_hi + 1) if want_bottom else range(rank_hi, rank_lo - 1, -1)
        ranks = list(ranks)
        # Check corners first based on typical placement (White low/bottom, Black high/top)
        cols_to_check = [1, 8, 2, 7, 3, 6, 4, 5]
        
        if ai_owners == ("neutral",):
            # Target middle columns and average rank for Neutral AI
            neutral_ranks = [p["rank"] for p in gs.all_pieces() if p["owner"] == "neutral"]
            if neutral_ranks:
                avg_r = sum(neutral_ranks) // len(neutral_ranks)
                valid_ranks = list(range(rank_lo, rank_hi + 1))
                ranks = sorted(valid_ranks, key=lambda r: abs(r - avg_r))
            cols_to_check = [4, 5, 3, 6, 2, 7, 1, 8]
        
        empty_squares = []
        for r in ranks:
            for c in cols_to_check:
                sq = (r, c)
                if gs.get(r, c) is None:  # Must be empty
                    empty_squares.append(sq)
                    if self._is_square_safe(sq, gs, active_color, ai_owners, use_cache=False):
                        return sq
        
        if empty_squares:
            return empty_squares[0]
            
        return None  # Failed to find safe square

    def _check_tactical_overrides(self, gs, ai_owners: tuple[str, ...]) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """
        Evaluate Hard Cases / Tactical Overrides in strict priority order.
        Priority 1: Capture Enemy King
        Priority 2: Capture Enemy Queen using weaker piece
        Priority 3: Safe Neutral Pawn Promotion at the board edges
        Priority 4: Capture Enemy Rook using weaker piece
        Priority 5: Capture Enemy Bishop/Knight using Pawn
        """
        from move_validator import get_legal_moves

        best_pri = 99
        best_override = None
        
        check_major = self.difficulty in ("medium", "hard", "insane")
        check_minor = self.difficulty in ("hard", "insane")
        
        cycles_until_shrink = 15 - ((gs.cycle - 1) % 15)
        is_danger_cycle = cycles_until_shrink <= 2 and gs.cycle <= 45
        danger_ranks = {gs.min_playable_rank, gs.min_playable_rank + 1, gs.max_playable_rank - 1, gs.max_playable_rank} if is_danger_cycle else set()

        if is_danger_cycle:
            evac_candidates = []
            for from_sq, piece in gs.board.items():
                if piece["owner"] in ai_owners and from_sq[0] in danger_ranks:
                    evac_candidates.append((from_sq, piece))
            
            if evac_candidates:
                from constants import PIECE_VALUES
                evac_candidates.sort(key=lambda x: PIECE_VALUES.get(x[1]["type"], 0), reverse=True)
                for from_sq, piece in evac_candidates:
                    legal_targets = get_legal_moves(from_sq, gs)
                    for to_sq in legal_targets:
                        if to_sq[0] not in danger_ranks:
                            if self._is_square_safe(to_sq, gs, "w", ai_owners):
                                log.info(f"[{self.__class__.__name__}] EVACUATION OVERRIDE! Rescuing {piece['type']} from {from_sq} to {to_sq}")
                                return (from_sq, to_sq)

        for from_sq, piece in gs.board.items():
            if piece["owner"] not in ai_owners:
                continue
                
            legal_targets = get_legal_moves(from_sq, gs)
            for to_sq in legal_targets:
                target = gs.get(*to_sq)
                is_capture = target and target["owner"] not in ai_owners
                target_type = target["type"] if is_capture else None
                
                # Rule 2: Danger Zone Avoidance. Do not move into a danger rank unless capturing King.
                if to_sq[0] in danger_ranks and target_type != "K":
                    continue
                
                pri = 99
                
                # Priority 1: King Capture
                if target_type == "K":
                    log.info(f"[{self.__class__.__name__}] INSTAKILL OVERRIDE! {piece['type']} captures King at {to_sq}")
                    return (from_sq, to_sq) # Highest priority, execute instantly
                    
                # Priority 2: Queen Capture (by weaker piece)
                elif check_major and target_type == "Q" and piece["type"] in ("P", "N", "B", "R"):
                    pri = 2
                    
                # Priority 3: Safe Pawn Promotion (Neutral only)
                elif piece["owner"] == "neutral" and piece["type"] == "P" and to_sq[0] in (gs.min_playable_rank, gs.max_playable_rank):
                    # verify destination is safe
                    if self._is_square_safe(to_sq, gs, "w", ai_owners): # "w" is safely ignored by _is_square_safe
                        pri = 3
                        
                # Priority 4: Rook Capture (by weaker piece)
                elif check_major and target_type == "R" and piece["type"] in ("P", "N", "B"):
                    pri = 4
                    
                # Priority 5: Minor Capture (by weaker Pawn)
                elif check_minor and target_type in ("B", "N") and piece["type"] == "P":
                    pri = 5

                # Compare and assign if it's the best override found so far
                if pri < best_pri:
                    best_pri = pri
                    best_override = (from_sq, to_sq)

        if best_override:
            pri_names = {2: "Queen Capture", 3: "Safe Pawn Promotion", 4: "Rook Capture", 5: "Minor Capture"}
            reason = pri_names.get(best_pri, "Unknown")
            log.info(f"[{self.__class__.__name__}] TACTICAL OVERRIDE [{reason}] at {best_override[0]} -> {best_override[1]}")
            return best_override
            
        return None

    def _find_rescue_move(
        self,
        gs,
        ai_owners: tuple[str, ...],
        min_value_to_save: int = 3,
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """
        Stage 1.5 — Rescue Override.

        Scans all AI-owned pieces (excluding Pawns and Kings) to find any that
        are currently attacked by a *cheaper* enemy piece (a losing exchange).
        If found, returns a move that escapes the threatened piece to a safe square.

        Rescue priority:
          - Highest-value piece first (Queen before Rook, etc.).
          - Only fires on STRICT losing exchanges: attacker_value < piece_value.
          - Equal-value exchanges are intentionally left for Stockfish to decide.
          - Pawns (value=1) and Kings are never rescued here.

        Returns (from_sq, to_sq) for the escape move, or None if no rescue needed.
        """
        from move_validator import get_legal_moves
        from constants import PIECE_VALUES

        # 1. Collect AI pieces that are in danger from a cheaper attacker
        threatened = []
        for sq, piece in gs.board.items():
            if piece["owner"] not in ai_owners:
                continue
            pv = PIECE_VALUES.get(piece["type"], 0)
            if pv < min_value_to_save:
                continue  # Skip Pawns (1pt) and Kings (20pt sentinel)

            # Find the cheapest enemy piece that can legally reach this square
            min_attacker_val = 999
            for a_sq, a_piece in gs.board.items():
                if a_piece["owner"] in ai_owners:
                    continue  # Friendly piece — not a threat
                a_val = PIECE_VALUES.get(a_piece["type"], 0)
                if a_val >= pv:
                    # Equal or more expensive attacker — not a losing exchange,
                    # let Stockfish handle this trade.
                    continue
                a_targets = get_legal_moves(a_sq, gs, ignore_turn=True)
                if sq in a_targets:
                    min_attacker_val = min(min_attacker_val, a_val)

            if min_attacker_val < pv:  # Strict losing exchange confirmed
                threatened.append((sq, piece, pv, min_attacker_val))

        if not threatened:
            return None

        # 2. Sort by descending piece value — rescue the most valuable piece first
        threatened.sort(key=lambda x: x[2], reverse=True)

        for t_sq, t_piece, pv, atk_val in threatened:
            legal_targets = get_legal_moves(t_sq, gs)
            # Prefer destinations that are confirmed safe from all enemies
            safe_escapes = [
                dst for dst in legal_targets
                if self._is_square_safe(dst, gs, "w", ai_owners)
            ]
            if safe_escapes:
                # Pick the first safe escape (simple greedy; Stockfish refines
                # the exact destination choice in normal eval turns)
                escape_sq = safe_escapes[0]
                log.info(
                    f"[{self.__class__.__name__}] RESCUE OVERRIDE! Moving {t_piece['type']} "
                    f"from {t_sq} to {escape_sq} "
                    f"(threatened by {atk_val}-pt piece, own value {pv}-pt)"
                )
                return (t_sq, escape_sq)

        # Threatened but no safe escape square found — let Stockfish decide
        log.debug("[%s] Rescue needed but no safe escape found; deferring to engine.", self.__class__.__name__)
        return None


    def _board_to_fen(self, gs, rank_lo: int, rank_hi: int, ai_owners: tuple[str, ...], active_color: str, side_to_move: str, remove_kings: list[str]) -> str:
        """
        Convert an 8x8 slice to FEN format.
        active_color: "w" or "b". Dictates how pieces map.
        If active_color == "w": AI is Uppercase, Enemies are Lowercase.
        If active_color == "b": AI is Lowercase, Enemies are Uppercase.
        
        side_to_move: "w" or "b". Determines whose turn it is in the resulting FEN.
        
        remove_kings: list of owner strings whose Kings should be stripped from the FEN 
        (to prevent Stockfish "Two Kings" crash).
        """
        fen_rows = []
        has_white_king = False
        has_black_king = False
        
        cycles_until_shrink = 15 - ((gs.cycle - 1) % 15)
        danger_ranks = []
        if cycles_until_shrink <= 2 and gs.cycle <= 45:
            danger_ranks = [gs.min_playable_rank, gs.min_playable_rank + 1, gs.max_playable_rank - 1, gs.max_playable_rank]
        
        # 1. Map pieces in the 8x8 window
        for r in range(rank_hi, rank_lo - 1, -1):
            empty_count = 0
            row_str = ""
            for c in range(1, 9):
                piece = gs.get(r, c)
                
                # Ghost pieces on danger ranks
                if piece and r in danger_ranks:
                    piece = None
                    
                char_to_add = None
                
                if piece:
                    # Strip kings of specified owners
                    if piece["type"] == "K" and piece["owner"] in remove_kings:
                        pass # Treat as empty
                    else:
                        is_friendly = piece["owner"] in ai_owners
                        char = piece["type"]
                        
                        if active_color == "w":
                            if is_friendly:
                                char = char.upper()
                                if char == 'K': has_white_king = True
                            else:
                                char = char.lower()
                                if char == 'k': has_black_king = True
                        else:
                            if is_friendly:
                                char = char.lower()
                                if char == 'k': has_black_king = True
                            else:
                                char = char.upper()
                                if char == 'K': has_white_king = True
                                
                        char_to_add = char

                if char_to_add:
                    if empty_count > 0:
                        row_str += str(empty_count)
                        empty_count = 0
                    row_str += char_to_add
                else:
                    empty_count += 1
                    
            if empty_count > 0:
                row_str += str(empty_count)
            fen_rows.append(row_str)

        # 2. Dummy King Injection
        if not has_white_king:
            want_bottom = True # Bottom right usually
            safe_sq = self._find_safe_dummy_king_square(gs, rank_lo, rank_hi, active_color, ("white",), want_bottom)
            if safe_sq:
                r, c = safe_sq
                # Rank offset from top of FEN: rank_hi - r
                fen_r = rank_hi - r
                col_idx = c - 1
                row_split = []
                for char in fen_rows[fen_r]:
                    if char.isdigit():
                        row_split.extend(['1'] * int(char))
                    else:
                        row_split.append(char)
                row_split[col_idx] = 'K'
                
                new_row = ""
                emp = 0
                for ch in row_split:
                    if ch == '1':
                        emp += 1
                    else:
                        if emp > 0:
                            new_row += str(emp)
                            emp = 0
                        new_row += ch
                if emp > 0: new_row += str(emp)
                fen_rows[fen_r] = new_row
            else:
                # If we couldn't find a safe square, just shove it in the first empty square
                found = False
                for r in range(rank_lo, rank_hi + 1):
                    fen_r = rank_hi - r
                    row_split = []
                    for char in fen_rows[fen_r]:
                        if char.isdigit():
                            row_split.extend(['1'] * int(char))
                        else:
                            row_split.append(char)
                            
                    for c in range(1, 9):
                        col_idx = c - 1
                        if col_idx < len(row_split) and row_split[col_idx] == '1': # Empty
                            row_split[col_idx] = 'K'
                            
                            new_row = ""
                            emp = 0
                            for ch in row_split:
                                if ch == '1':
                                    emp += 1
                                else:
                                    if emp > 0:
                                        new_row += str(emp)
                                        emp = 0
                                    new_row += ch
                            if emp > 0:
                                new_row += str(emp)
                                
                            fen_rows[fen_r] = new_row
                            found = True
                            break
                    if found:
                        break
                log.warning("[%s] Failed to find safe square for White Dummy King", self.__class__.__name__)
                
        if not has_black_king:
            want_bottom = False # Top left usually
            safe_sq = self._find_safe_dummy_king_square(gs, rank_lo, rank_hi, active_color, ("black",), want_bottom)
            if safe_sq:
                r, c = safe_sq
                fen_r = rank_hi - r
                col_idx = c - 1
                row_split = []
                for char in fen_rows[fen_r]:
                    if char.isdigit():
                        row_split.extend(['1'] * int(char))
                    else:
                        row_split.append(char)
                row_split[col_idx] = 'k'
                
                new_row = ""
                emp = 0
                for ch in row_split:
                    if ch == '1':
                        emp += 1
                    else:
                        if emp > 0:
                            new_row += str(emp)
                            emp = 0
                        new_row += ch
                if emp > 0: new_row += str(emp)
                fen_rows[fen_r] = new_row
            else:
                log.warning("[%s] Failed to find safe square for Black Dummy King", self.__class__.__name__)
        
        # 3. Assemble full FEN
        board_part = "/".join(fen_rows)
        fen = f"{board_part} {side_to_move} - - 0 1"
        return fen

    def _evaluate_subboard(self, gs, rank_lo: int, rank_hi: int, ai_owners: tuple[str, ...], board_name: str, active_color: str, remove_kings: list[str]) -> list[dict]:
        fen = self._board_to_fen(gs, rank_lo, rank_hi, ai_owners, active_color, active_color, remove_kings)
        log.debug("[%s] %s FEN: %s", self.__class__.__name__, board_name, fen)

        # Use our own syntax-only FEN check instead of engine.is_fen_valid().
        # The library's is_fen_valid() internally spawns a NEW Stockfish subprocess
        # on every call (with no CREATE_NO_WINDOW), causing visible console flashes.
        if not _is_fen_syntax_valid(fen):
            log.warning("[%s] Invalid FEN generated for %s!", self.__class__.__name__, board_name)
            return []
            
        self.engine.set_fen_position(fen)
        
        try:
            eval_before = self.engine.get_evaluation()
            base_cp = eval_before.get("value", 0)
            if eval_before.get("type") == "mate":
                base_cp = 10000 if eval_before["value"] > 0 else -10000
                
            top_moves = self.engine.get_top_moves(5)
            log.debug("[%s] Evaluating top %d moves for %s (Base CP: %d)", self.__class__.__name__, len(top_moves), board_name, base_cp)
            
        except Exception as e:
            log.error("[%s] ENGINE CRASH on %s! Exception: %s", self.__class__.__name__, board_name, e)
            log.error("[%s] Crashing FEN: %s", self.__class__.__name__, fen)
            self.quit()
            try:
                self.engine = _make_stockfish_engine(install_stockfish_engine(), self._engine_depth)
            except Exception as restart_err:
                log.error("[%s] Failed to restart engine after crash: %s", self.__class__.__name__, restart_err)
            return []
            
        results = []
        for move in top_moves:
            sf_move = move["Move"][:4]
            c1 = ord(sf_move[0]) - ord('a') + 1
            r1 = int(sf_move[1]) + rank_lo - 1
            c2 = ord(sf_move[2]) - ord('a') + 1
            r2 = int(sf_move[3]) + rank_lo - 1
            
            cp_after = move.get("Centipawn", 0)
            if move.get("Mate"):
                cp_after = 10000 if move["Mate"] > 0 else -10000
                
            swing = cp_after - base_cp
            
            log.debug("[%s]   Move %s (kt: %s,%s -> %s,%s) | CP After: %d | Swing: %+d", self.__class__.__name__, 
                      sf_move, r1, c1, r2, c2, cp_after, swing)
            
            results.append({
                "from_sq": (r1, c1),
                "to_sq": (r2, c2),
                "swing": swing,
                "subboard": board_name,
                "sf_move": sf_move
            })
            
        return results

    def choose_move(self, gs) -> tuple[tuple[int, int], tuple[int, int]] | None:
        raise NotImplementedError("Subclasses must implement choose_move()")
