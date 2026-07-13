import time
import logging
from constants import PIECE_VALUES, PLAYABLE_MIN, PLAYABLE_MAX
from move_validator import is_legal_move
from .base_stockfish import BaseStockfishAI

log = logging.getLogger("KingsTrial.ai.neutral")

class NeutralAI(BaseStockfishAI):
    def _find_target_board(self, gs, min_r: int, max_r: int, scan_down: bool) -> tuple[int, int] | None:
        """
        Scan for a board of 8 ranks that contains >= 15 pts and >= 2 Neutral pieces.
        If scan_down is True, iterate backwards from max_r to min_r + 7.
        If scan_down is False, iterate forwards from min_r to max_r - 7.
        Returns (rank_lo, rank_hi) or None.
        """
        # Define ranges:
        if scan_down:
            range_scan = range(max_r, min_r + 7 - 1, -1)
        else:
            range_scan = range(min_r, max_r - 7 + 1)
            
        best_val = -1
        best_window = None
        
        for primary_rank in range_scan:
            if scan_down:
                hi = primary_rank
                lo = hi - 7
            else:
                lo = primary_rank
                hi = lo + 7
                
            val = 0
            neutral_count = 0
            for r in range(lo, hi + 1):
                for c in range(1, 9):
                    p = gs.get(r, c)
                    if p:
                        val += PIECE_VALUES.get(p["type"], 0)
                        if p["owner"] == "neutral":
                            neutral_count += 1
                            
            if neutral_count >= 2 and val >= 15:
                return (lo, hi)
            elif neutral_count > 0:
                if val > best_val:
                    best_val = val
                    best_window = (lo, hi)
                    
        return best_window

    def choose_move(self, gs) -> tuple[tuple[int, int], tuple[int, int]] | None:
        try:
            return self._choose_move_internal(gs)
        except Exception as e:
            log.error(f"[NeutralAI] Engine crashed during choose_move: {e}", exc_info=True)
            try:
                from ai.base_stockfish import install_stockfish_engine, _make_stockfish_engine
                self.engine = _make_stockfish_engine(install_stockfish_engine(), self._engine_depth)
                log.info("[NeutralAI] Engine successfully restarted after crash.")
            except Exception as e2:
                log.error(f"[NeutralAI] Failed to restart engine: {e2}")
            return self._get_fallback_move(gs)

    def _choose_move_internal(self, gs) -> tuple[tuple[int, int], tuple[int, int]] | None:
        if not self.available or self.engine is None:
            log.debug("[NeutralAI] Engine unavailable; falling back to random move selection.")
            return self._get_fallback_move(gs)

        log.debug("[NeutralAI] Start Neural Evaluation Cycle")
        ai_owners = ("neutral",)
        
        self.current_attacked_squares = self._generate_attacked_squares(gs, ai_owners)
        
        # Stage 1: Tactical overrides (instakill, captures, pawn promotions)
        override_move = self._check_tactical_overrides(gs, ai_owners)
        if override_move:
            return override_move

        # Stage 1.5: Rescue Override — save major/minor pieces threatened by a
        # cheaper attacker. Only triggers on strict losing exchanges
        # (attacker_value < piece_value). Equal-value trades are left to Stockfish.
        rescue_move = self._find_rescue_move(gs, ai_owners, min_value_to_save=3)
        if rescue_move:
            return rescue_move

        candidate_moves = {}
        start_time = time.time()
        
        mid_rank = (PLAYABLE_MIN + PLAYABLE_MAX) // 2
        
        cycles_until_shrink = 15 - ((gs.cycle - 1) % 15)
        is_danger_cycle = cycles_until_shrink <= 2 and gs.cycle <= 45
        danger_ranks = {gs.min_playable_rank, gs.min_playable_rank + 1, gs.max_playable_rank - 1, gs.max_playable_rank} if is_danger_cycle else set()
        
        # Determine number of boards to evaluate based on difficulty
        eval_high = True
        eval_low = True
        eval_mid = self.difficulty in ("hard", "insane")
        
        # Stage 2: Sub-Board Stockfish Evaluation
        # 1. High Board (North - upper half)
        if eval_high:
            north_window = self._find_target_board(gs, min_r=mid_rank, max_r=PLAYABLE_MAX, scan_down=True)
            if north_window:
                lo, hi = north_window
                log.debug(f"[NeutralAI] Evaluating High Board [{lo}-{hi}] as White")
                # Evaluate as White (pushing down). Player White King acts as enemy if present, so remove it.
                moves = self._evaluate_subboard(gs, lo, hi, ai_owners, "North Board", "w", remove_kings=["white"])
                for m in moves:
                    move_pair = (m["from_sq"], m["to_sq"])
                    if is_legal_move(move_pair[0], move_pair[1], gs):
                        if move_pair[1][0] not in danger_ranks:
                            candidate_moves[move_pair] = candidate_moves.get(move_pair, 0) + m["swing"]

        # 2. Low Board (South - lower half)
        if eval_low:
            south_window = self._find_target_board(gs, min_r=PLAYABLE_MIN, max_r=mid_rank, scan_down=False)
            if south_window:
                lo, hi = south_window
                log.debug(f"[NeutralAI] Evaluating Low Board [{lo}-{hi}] as Black")
                # Evaluate as Black (pushing up). Player Black King acts as enemy if present, so remove it.
                moves = self._evaluate_subboard(gs, lo, hi, ai_owners, "South Board", "b", remove_kings=["black"])
                for m in moves:
                    move_pair = (m["from_sq"], m["to_sq"])
                    if is_legal_move(move_pair[0], move_pair[1], gs):
                        if move_pair[1][0] not in danger_ranks:
                            candidate_moves[move_pair] = candidate_moves.get(move_pair, 0) + m["swing"]
                        
        # 3. Central Hotzone (Spanning mid_rank boundary)
        if eval_mid:
            # Anchor window around the mid rank
            lo = mid_rank - 3
            hi = lo + 7
            
            log.debug(f"[NeutralAI] Evaluating Central Board [{lo}-{hi}] Dual Direction")
            moves_w = self._evaluate_subboard(gs, lo, hi, ai_owners, "Central Board (W)", "w", remove_kings=["white", "black"])
            moves_b = self._evaluate_subboard(gs, lo, hi, ai_owners, "Central Board (B)", "b", remove_kings=["white", "black"])
            
            for m in moves_w + moves_b:
                move_pair = (m["from_sq"], m["to_sq"])
                if is_legal_move(move_pair[0], move_pair[1], gs):
                    if move_pair[1][0] not in danger_ranks:
                        candidate_moves[move_pair] = candidate_moves.get(move_pair, 0) + m["swing"]

        # Stage 3: Final Selection
        if not candidate_moves:
            log.warning("[NeutralAI] No legal candidate moves found from engine! Falling back to random.")
            return self._get_fallback_move(gs)
            
        best_move = max(candidate_moves.items(), key=lambda x: x[1])
        
        log.info("[NeutralAI] Selected best move: %s -> %s with swing %+d", 
                 best_move[0][0], best_move[0][1], best_move[1])
                 
        return best_move[0]
