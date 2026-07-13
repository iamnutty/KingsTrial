import time
import logging
import traceback
from constants import PIECE_VALUES, BOARD_RANKS, PROMOTION_COST, MAX_PIECE_LIMITS
from move_validator import is_legal_move, get_all_legal_moves, get_legal_moves
from .base_stockfish import BaseStockfishAI, install_stockfish_engine, _make_stockfish_engine, _is_fen_syntax_valid

log = logging.getLogger("KingsTrial.ai.opponent")

class OpponentAI(BaseStockfishAI):

    def _get_fallback_move(self, gs):
        from move_validator import get_all_legal_moves
        import random
        from constants import PIECE_VALUES
        
        owner = gs.current_owner()
        ai_owners = (owner,)
        active_color = "w" if owner == "white" else "b"
        all_legal_moves = get_all_legal_moves(gs)
        k_sq = gs.find_king(owner)

        def simulate_is_safe(check_sq, move):
            from_sq, to_sq = move
            target_piece = gs.board.get(to_sq)
            piece = gs.board.pop(from_sq)
            gs.board[to_sq] = piece
            sq_to_check = to_sq if check_sq == from_sq else check_sq
            is_safe = self._is_square_safe(sq_to_check, gs, active_color, ai_owners, use_cache=False)
            gs.board[from_sq] = piece
            if target_piece: gs.board[to_sq] = target_piece
            else: del gs.board[to_sq]
            return is_safe

        safe_moves = [m for m in all_legal_moves if (not k_sq or simulate_is_safe(k_sq, m))]
        
        if safe_moves:
            # prioritize lowest value pieces
            safe_moves.sort(key=lambda m: PIECE_VALUES.get(gs.board.get(m[0], {}).get("type"), 999))
            cheapest_val = PIECE_VALUES.get(gs.board.get(safe_moves[0][0], {}).get("type"), 999)
            cheapest_moves = [m for m in safe_moves if PIECE_VALUES.get(gs.board.get(m[0], {}).get("type"), 999) == cheapest_val]
            return random.choice(cheapest_moves)
            
        if all_legal_moves:
            return random.choice(all_legal_moves)
        return None

    def _get_targeted_hotzone(self, gs, target_sq, attacker_sqs):
        """
        Returns an exactly 8-rank window that includes the target piece and its immediate +/- 1 rank moves,
        and includes as many attackers as possible. If an attacker is too far (> 7 ranks away), it will
        require a dummy attacker to be placed on the edge, which is handled downstream.
        """
        tr = target_sq[0]
        # Required ranks for the target piece (itself + immediate moves like King step)
        req_lo = max(gs.min_playable_rank, tr - 1)
        req_hi = min(gs.max_playable_rank, tr + 1)
        
        # Valid 8-rank windows that cover req_lo and req_hi
        valid_windows = []
        for lo in range(gs.min_playable_rank, gs.max_playable_rank - 8 + 2):
            hi = lo + 7
            if lo <= req_lo and hi >= req_hi:
                valid_windows.append((lo, hi))
                
        if not valid_windows:
            # Fallback if board is super constrained
            lo = max(gs.min_playable_rank, tr - 3)
            hi = min(gs.max_playable_rank, lo + 7)
            if hi - lo < 7: lo = hi - 7
            return lo, hi

        # Score windows by how many attackers they include, then total pieces
        best_window = valid_windows[0]
        best_score = -1
        
        for w_lo, w_hi in valid_windows:
            attackers_included = sum(1 for ar, ac in attacker_sqs if w_lo <= ar <= w_hi)
            pieces_included = 0
            for r in range(w_lo, w_hi + 1):
                for c in range(1, 9):
                    if gs.get(r, c):
                        pieces_included += 1
            
            score = (attackers_included * 100) + pieces_included
            if score > best_score:
                best_score = score
                best_window = (w_lo, w_hi)
                
        return best_window

    def choose_move(self, gs) -> tuple | None:
        try:
            return self._choose_move_internal(gs)
        except Exception as e:
            log.error(f"[OpponentAI] Engine crashed during choose_move: {e}", exc_info=True)
            self._restart_engine()
            return self._get_fallback_move(gs)

    def _restart_engine(self):
        try:
            from ai.base_stockfish import install_stockfish_engine, _make_stockfish_engine
            self.engine = _make_stockfish_engine(install_stockfish_engine(), self._engine_depth)
            log.info("[OpponentAI] Engine successfully restarted after crash.")
        except Exception as e2:
            log.error(f"[OpponentAI] Failed to restart engine: {e2}")

    def _choose_move_internal(self, gs) -> tuple | None:
        if not self.available or self.engine is None:
            return self._get_fallback_move(gs)

        log.debug("[OpponentAI] Start Opponent Evaluation Cycle")
        start_time = time.time()

        # ── Difficulty parameters ─────────────────────────────────────────────
        # Three levers that scale the existing pipeline without restructuring it:
        #
        #  timeout_mult   — scales (inc_sec × 2.5) that sets the thinking deadline.
        #                   Easy = 1.0× increment; Medium = 1.5×; Hard = full 2.5×.
        #                   The existing `if time.time() > deadline: break` guards
        #                   in every step naturally limit how much gets evaluated.
        #
        #  exec_threshold — minimum cp swing required to commit early and skip later
        #                   steps. Hard keeps the current 400/300; easier difficulties
        #                   use a higher bar so the AI rarely short-circuits and always
        #                   falls through to STEP 8 where noise is applied.
        #
        #  noise_pool_size — at STEP 8 (watchdog), pick randomly from the top-N
        #                   evaluated moves rather than always the single best.
        #                   Hard = 1 (always best, unchanged); Easy = 3 (most noise).
        _DIFF_PARAMS = {
            "easy":   {"timeout_mult": 1.0, "exec_threshold": 550, "noise_pool_size": 3},
            "medium": {"timeout_mult": 1.5, "exec_threshold": 350, "noise_pool_size": 2},
            "hard":   {"timeout_mult": 2.5, "exec_threshold": 400, "noise_pool_size": 1},
        }
        # "random" difficulty bypasses this method entirely — engine is None,
        # so the availability check above already routes to _get_fallback_move.
        dp = _DIFF_PARAMS.get(self.difficulty, _DIFF_PARAMS["hard"])
        log.info(
            f"[OpponentAI] Difficulty='{self.difficulty}' | "
            f"timeout_mult={dp['timeout_mult']}x, "
            f"exec_threshold={dp['exec_threshold']}cp, "
            f"noise_pool={dp['noise_pool_size']}"
        )

        # Use increment safely, default to 5.0 if missing
        inc_sec = gs.increment_sec if hasattr(gs, 'increment_sec') else 5.0
        # Scale the thinking deadline by difficulty multiplier
        timeout_limit = inc_sec * dp["timeout_mult"]
        deadline = start_time + timeout_limit
        log.debug(f"[OpponentAI] Deadline set: {timeout_limit:.1f}s (inc={inc_sec}s × {dp['timeout_mult']}x)")

        owner = gs.current_owner()
        ai_owners = (owner,)
        active_color = "w" if owner == "white" else "b"
        opp_color = "b" if active_color == "w" else "w"
        enemy_owners = tuple(o for o in ["white", "black", "neutral"] if o not in ai_owners)
        
        # Precompute attacked squares to speed up _is_square_safe checks
        self.current_attacked_squares = self._generate_attacked_squares(gs, ai_owners)
        
        all_legal_moves = get_all_legal_moves(gs)
        if not all_legal_moves:
            return None

        k_sq = gs.find_king(owner)
        target_rank = gs.max_playable_rank if owner == "white" else gs.min_playable_rank

        def simulate_is_safe(check_sq, move):
            from_sq, to_sq = move
            target_piece = gs.board.get(to_sq)
            piece = gs.board.pop(from_sq)
            gs.board[to_sq] = piece
            
            sq_to_check = to_sq if check_sq == from_sq else check_sq
            is_safe = self._is_square_safe(sq_to_check, gs, active_color, ai_owners, use_cache=False)
            
            gs.board[from_sq] = piece
            if target_piece:
                gs.board[to_sq] = target_piece
            else:
                del gs.board[to_sq]
            return is_safe

        # Helper to get CP swing with Dummy support
        def get_cp_swing(move_or_action, lo, hi, dummy_attackers=None):
            def setup_state_and_get_eval(is_after):
                # Apply dummies
                if dummy_attackers:
                    for d_sq, d_piece in dummy_attackers.items():
                        gs.board[d_sq] = d_piece

                # Apply action if after
                action_data = None
                if is_after:
                    if isinstance(move_or_action[0], tuple): # standard move
                        from_sq, to_sq = move_or_action
                        t_piece = gs.board.get(to_sq)
                        f_piece = gs.board.pop(from_sq)
                        gs.board[to_sq] = f_piece
                        action_data = (from_sq, to_sq, f_piece, t_piece)
                    elif move_or_action[0] == "PROMOTE":
                        _, sq, new_type = move_or_action
                        old_type = gs.board[sq]["type"]
                        gs.board[sq]["type"] = new_type
                        action_data = (sq, old_type)
                    elif move_or_action[0] == "SPAWN":
                        _, piece_type, sq = move_or_action
                        gs.board[sq] = {"type": piece_type, "owner": owner}
                        action_data = (sq,)

                stm = opp_color if is_after else active_color
                fen = self._board_to_fen(gs, lo, hi, ai_owners, active_color, stm, remove_kings=[])

                # Undo action
                if is_after:
                    if isinstance(move_or_action[0], tuple):
                        from_sq, to_sq, f_piece, t_piece = action_data
                        gs.board[from_sq] = f_piece
                        if t_piece: gs.board[to_sq] = t_piece
                        else: del gs.board[to_sq]
                    elif move_or_action[0] == "PROMOTE":
                        sq, old_type = action_data
                        gs.board[sq]["type"] = old_type
                    elif move_or_action[0] == "SPAWN":
                        sq, = action_data
                        del gs.board[sq]
                
                # Undo dummies
                if dummy_attackers:
                    for d_sq in dummy_attackers:
                        del gs.board[d_sq]

                # Use syntax-only check to avoid spawning a new Stockfish subprocess
                # (engine.is_fen_valid() internally creates a new process each call).
                if not _is_fen_syntax_valid(fen): return None
                self.engine.set_fen_position(fen)
                eval_res = self.engine.get_evaluation()
                if eval_res.get("type") == "cp":
                    return eval_res.get("value", 0)
                else:
                    return 10000 if eval_res.get("value", 0) > 0 else -10000

            try:
                base_cp = setup_state_and_get_eval(False)
                if base_cp is None: return -9999
                after_cp = setup_state_and_get_eval(True)
                if after_cp is None: return -9999
                
                # Stockfish evaluates from perspective of the active_color in the FEN.
                # Base State: evaluated for AI. (+100 means AI is ahead by 1 pawns)
                # After State: evaluated for Opponent. (+150 means Opponent is ahead by 1.5 pawns, AI is down 1.5 pawns)
                # AI's actual eval after move is -after_cp (-150).
                # Swing = (AI Eval After) - (AI Eval Base)
                return -after_cp - base_cp
            except Exception as e:
                log.error(f"[OpponentAI] Engine crash in get_cp_swing: {e}")
                self._restart_engine()
                return -9999

        def get_dummy_attackers(target_sq, w_lo, w_hi):
            dummies = {}
            for sq, p in gs.board.items():
                if p["owner"] in enemy_owners:
                    legal_targets = get_legal_moves(sq, gs, ignore_turn=True)
                    if target_sq in legal_targets:
                        ar, ac = sq
                        if not (w_lo <= ar <= w_hi):
                            # It's outside the window. Project it onto the edge.
                            edge_r = w_hi if ar > w_hi else w_lo if ar < w_lo else ar
                            dummy_sq = (edge_r, ac)
                            # Only place if empty
                            if dummy_sq not in gs.board:
                                dummies[dummy_sq] = p
            return dummies

        top_moves_so_far = []   # Moves tied at the current maximum swing
        top_swing_so_far = -9999

        # Parallel pool that records every (swing, move) evaluated anywhere in the
        # pipeline. Used only at STEP 8 for noise-calibrated final selection:
        # on Easy/Medium the AI picks from the top-N evaluated moves instead of
        # always the single best, introducing human-like imprecision without
        # changing how the evaluation itself works. Hard leaves this unused.
        all_candidates: list[tuple[int, tuple]] = []

        def update_top_move(move, swing):
            nonlocal top_moves_so_far, top_swing_so_far
            all_candidates.append((swing, move))  # Record for noise pool at STEP 8
            if swing > top_swing_so_far:
                top_swing_so_far = swing
                top_moves_so_far = [move]
            elif swing == top_swing_so_far:
                top_moves_so_far.append(move)

        # STEP 1: Insta-Win
        if k_sq:
            for move in all_legal_moves:
                if move[0] == k_sq and move[1][0] == target_rank:
                    log.info(f"[OpponentAI] STEP 1 INSTA-WIN: Moving King to winning rank at {move[1]}")
                    return move

        # STEP 2: Instakill (Capture Enemy King)
        for move in all_legal_moves:
            target = gs.board.get(move[1])
            if target and target["type"] == "K" and target["owner"] in enemy_owners:
                if gs.board.get(move[0], {}).get("type") == "K":
                    if not simulate_is_safe(move[1], move):
                        continue
                log.info(f"[OpponentAI] STEP 2 INSTAKILL: Capturing King at {move[1]}")
                return move

        # STEP 3: King Defense
        if k_sq and not self._is_square_safe(k_sq, gs, active_color, ai_owners):
            log.info("[OpponentAI] STEP 3 King Defense: King is in danger!")
            attackers = []
            for sq, p in gs.board.items():
                if p["owner"] in enemy_owners:
                    if k_sq in get_legal_moves(sq, gs, ignore_turn=True):
                        attackers.append(sq)
            
            w_lo, w_hi = self._get_targeted_hotzone(gs, k_sq, attackers)
            dummies = get_dummy_attackers(k_sq, w_lo, w_hi)
            
            candidate_escapes = [m for m in all_legal_moves if simulate_is_safe(k_sq, m)]
            best_escapes = []
            best_escape_swing = -9999
            
            for move in candidate_escapes:
                if time.time() > deadline: break
                swing = get_cp_swing(move, w_lo, w_hi, dummy_attackers=dummies)
                if swing > best_escape_swing:
                    best_escape_swing = swing
                    best_escapes = [move]
                elif swing == best_escape_swing:
                    best_escapes.append(move)
            
            if best_escapes:
                import random
                best_escape = random.choice(best_escapes)
                log.info(f"[OpponentAI] STEP 3 EXECUTED: Escape {best_escape} with swing {best_escape_swing}")
                return best_escape
            elif candidate_escapes:
                log.info(f"[OpponentAI] STEP 3 EXECUTED: Fallback escape {candidate_escapes[0]}")
                return candidate_escapes[0]

        # Get King-safe moves for the rest of the steps
        safe_moves = [m for m in all_legal_moves if (not k_sq or simulate_is_safe(k_sq, m))]

        if not safe_moves:
            log.warning("[OpponentAI] No king-safe moves found. Falling back to random.")
            return self._get_fallback_move(gs)

        # STEP 4: Major/Minor Tactics (Captures & Evasions)
        log.info("[OpponentAI] STEP 4: Major/Minor Tactics")
        tactical_moves = set()
        
        # Evasions
        for sq, p in list(gs.board.items()):
            if p["owner"] in ai_owners and p["type"] not in ("K", "P"):
                if not self._is_square_safe(sq, gs, active_color, ai_owners):
                    for move in safe_moves:
                        if move[0] == sq and simulate_is_safe(move[1], move): tactical_moves.add(move)
                        elif move[1] == sq and simulate_is_safe(sq, move): tactical_moves.add(move)
        
        # Captures
        for move in safe_moves:
            target = gs.board.get(move[1])
            if target and target["owner"] in enemy_owners and target["type"] not in ("K", "P"):
                tactical_moves.add(move)

        if tactical_moves and time.time() <= deadline:
            for move in tactical_moves:
                if time.time() > deadline: break
                from_sq, to_sq = move
                target_sq = from_sq if gs.board.get(from_sq) else to_sq
                attackers = [sq for sq, p in gs.board.items() if p["owner"] in enemy_owners and target_sq in get_legal_moves(sq, gs, ignore_turn=True)]
                w_lo, w_hi = self._get_targeted_hotzone(gs, target_sq, attackers)
                dummies = get_dummy_attackers(target_sq, w_lo, w_hi)
                
                swing = get_cp_swing(move, w_lo, w_hi, dummy_attackers=dummies)
                
                # Material Delta Infusion for Captures
                target_piece = gs.board.get(to_sq)
                if target_piece and target_piece["owner"] in enemy_owners:
                    val = PIECE_VALUES.get(target_piece["type"], 0)
                    swing += (val * 100)
                    
                update_top_move(move, swing)
            
            log.info(f"[OpponentAI] STEP 4 top moves: {len(top_moves_so_far)} options with swing {top_swing_so_far}")
            # Commit early if the tactical swing already beats the difficulty threshold.
            # Hard commits at 400 cp (current behaviour); easier difficulties need a
            # larger swing before short-circuiting, so they fall through to later steps.
            if top_swing_so_far > dp["exec_threshold"]:
                import random
                top_move = random.choice(top_moves_so_far)
                log.info(
                    f"[OpponentAI] STEP 4 EXECUTED: swing {top_swing_so_far} "
                    f"> threshold {dp['exec_threshold']}"
                )
                return top_move

        # STEP 5: Promotions
        log.info("[OpponentAI] STEP 5: Promotions")
        my_pts = gs.points[owner]
        if time.time() <= deadline:
            for sq, p in gs.board.items():
                if time.time() > deadline: break
                if p["owner"] == owner and p["type"] != "K":
                    if self._is_square_safe(sq, gs, active_color, ai_owners): # Not under attack
                        # Evaluate ALL possible affordable promotions
                        for new_type, cost in PROMOTION_COST.items():
                            if new_type != p["type"] and my_pts >= cost:
                                # Check piece limits
                                current_count = sum(1 for piece in gs.board.values() if piece["owner"] == owner and piece["type"] == new_type)
                                if current_count < MAX_PIECE_LIMITS.get(new_type, 99):
                                    action = ("PROMOTE", sq, new_type)
                                    w_lo, w_hi = self._get_targeted_hotzone(gs, sq, [])
                                    swing = get_cp_swing(action, w_lo, w_hi)
                                    swing -= (cost * 50)
                                    update_top_move(action, swing)

            log.info(f"[OpponentAI] STEP 5 top moves so far: {len(top_moves_so_far)} options with swing {top_swing_so_far}")
            # Same early-exit threshold as STEP 4 — promotions are treated equally
            # to tactical captures in terms of commitment urgency.
            if top_swing_so_far > dp["exec_threshold"]:
                import random
                top_move = random.choice(top_moves_so_far)
                log.info(
                    f"[OpponentAI] STEP 5 EXECUTED: Promotion swing {top_swing_so_far} "
                    f"> threshold {dp['exec_threshold']}"
                )
                return top_move

        # STEP 6: Positional Play via Engine Query
        log.info("[OpponentAI] STEP 6: Positional Play via Engine Query")
        if time.time() <= deadline:
            target_sq = k_sq
            if not target_sq:
                owned = [sq for sq, p in gs.board.items() if p["owner"] in ai_owners]
                if owned: target_sq = owned[0]
                
            if target_sq:
                lo, hi = self._get_targeted_hotzone(gs, target_sq, [])
                stm = active_color
                fen = self._board_to_fen(gs, lo, hi, ai_owners, active_color, stm, remove_kings=[])
                
                # Use syntax-only check to avoid spawning a new Stockfish subprocess.
                if _is_fen_syntax_valid(fen):
                    self.engine.set_fen_position(fen)
                    top_engine_moves = self.engine.get_top_moves(3)
                    
                    for tm in top_engine_moves:
                        if time.time() > deadline: break
                        engine_move = tm["Move"][:4] # e.g. "e2e4", strip promotion char
                        from_c = ord(engine_move[0]) - ord('a') + 1
                        from_r = lo + int(engine_move[1]) - 1
                        to_c = ord(engine_move[2]) - ord('a') + 1
                        to_r = lo + int(engine_move[3]) - 1
                        
                        move = ((from_r, from_c), (to_r, to_c))
                        
                        if move in safe_moves:
                            swing = get_cp_swing(move, lo, hi)
                            
                            # Bonus/Penalty for King moves
                            if move[0] == k_sq:
                                kr = k_sq[0]
                                is_forward = (owner == "white" and move[1][0] > kr) or (owner == "black" and move[1][0] < kr)
                                is_backward = (owner == "white" and move[1][0] < kr) or (owner == "black" and move[1][0] > kr)
                                if is_forward:
                                    kr_to = move[1][0]
                                    d = gs.max_playable_rank - kr_to if owner == "white" else kr_to - gs.min_playable_rank
                                    d_max = gs.max_playable_rank - gs.min_playable_rank
                                    if d_max > 1:
                                        progress = max(0.0, min(1.0, (d_max - d) / (d_max - 1)))
                                        bonus = 100 + (400 * progress)
                                    else:
                                        bonus = 500
                                    swing += bonus
                                elif is_backward:
                                    swing -= 50
                                    
                            update_top_move(move, swing)
            
            log.info(f"[OpponentAI] STEP 6 completed. Final top moves: {len(top_moves_so_far)} options with swing {top_swing_so_far}")

        # STEP 7: Spawning (Only evaluated if previous steps yielded poor swings)
        log.info("[OpponentAI] STEP 7: Spawning")
        if time.time() <= deadline and k_sq and top_swing_so_far <= 100:
            kr, kc = k_sq

            # Build the list of piece types eligible for spawning.
            # Pawns have infinite supply; all other types require a piece
            # in the respawn pool (matching execute_respawn logic).
            pool = gs.respawn_pool.get(owner, [])
            pool_types = {p["type"] for p in pool}
            eligible_spawn_types = {
                pt: v for pt, v in PIECE_VALUES.items()
                if pt not in ("K",) and (pt == "P" or pt in pool_types)
            }

            for piece_type, value in eligible_spawn_types.items():
                cost = value
                
                if cost <= gs.points[owner]:
                    # Limit counts
                    curr_count = sum(1 for sq, p in gs.board.items() if p["owner"] == owner and p["type"] == piece_type)
                    if curr_count >= MAX_PIECE_LIMITS.get(piece_type, 2):
                        continue
                        
                    # Adjacent squares
                    for dr in [-1, 0, 1]:
                        for dc in [-1, 0, 1]:
                            if dr == 0 and dc == 0: continue
                            if time.time() > deadline: break
                            
                            sq = (kr + dr, kc + dc)
                            if 1 <= sq[1] <= 8 and gs.min_playable_rank <= sq[0] <= gs.max_playable_rank:
                                if gs.board.get(sq) is None:
                                    if piece_type != "P" and not self._is_square_safe(sq, gs, active_color, ai_owners):
                                        continue # Don't spawn major pieces onto attacked squares
                                    
                                    action = ("SPAWN", piece_type, sq)
                                    w_lo, w_hi = self._get_targeted_hotzone(gs, sq, [])
                                    swing = get_cp_swing(action, w_lo, w_hi)
                                    swing -= (value * 50)
                                    update_top_move(action, swing)

            log.info(f"[OpponentAI] STEP 7 completed. Top moves so far: {len(top_moves_so_far)} options with swing {top_swing_so_far}")
            # Spawning is a fallback option — its commit threshold is set 100 cp below
            # the main exec_threshold, preserving the design intent that a spawn needs
            # to be a meaningfully good move but doesn't need to be as dominant as a
            # capture or promotion to justify committing early.
            spawn_threshold = dp["exec_threshold"] - 100
            if top_swing_so_far > spawn_threshold:
                import random
                top_move = random.choice(top_moves_so_far)
                log.info(
                    f"[OpponentAI] STEP 7 EXECUTED: Spawn swing {top_swing_so_far} "
                    f"> threshold {spawn_threshold}"
                )
                return top_move

        # STEP 8: Watchdog Execution — Noise-Calibrated Final Pick
        #
        # Hard (noise_pool_size=1): always plays the single best accumulated move.
        #   Behaviour is identical to the original code.
        #
        # Medium/Easy (pool_size=2/3): sorts all_candidates by swing descending,
        #   deduplicates, and picks uniformly at random from the top-N. The AI
        #   evaluated correctly throughout — noise only affects which of the good
        #   moves it actually plays, mimicking human-like execution imprecision.
        #
        # The sort + dedup over all_candidates is O(n log n) on ~20–50 items —
        # microseconds, not perceptible.
        import random

        if all_candidates and dp["noise_pool_size"] > 1:
            all_candidates.sort(key=lambda x: x[0], reverse=True)

            # Deduplicate: keep first occurrence of each distinct move in swing order
            seen: set = set()
            noise_pool: list[tuple[int, tuple]] = []
            for swing, move in all_candidates:
                # Build a hashable key that works for both regular moves (tuple of tuples)
                # and action moves ("SPAWN"/"PROMOTE" + args)
                key = move if isinstance(move[0], tuple) else tuple(move)
                if key not in seen:
                    seen.add(key)
                    noise_pool.append((swing, move))
                if len(noise_pool) >= dp["noise_pool_size"]:
                    break

            chosen_swing, top_move = random.choice(noise_pool)
            best_swing = all_candidates[0][0]
            log.info(
                f"[OpponentAI] STEP 8 (noise): Picked from pool of {len(noise_pool)} moves "
                f"| best_swing={best_swing}, chosen_swing={chosen_swing}, "
                f"pool_size={dp['noise_pool_size']}"
            )
            return top_move

        # Hard difficulty or fallback: always execute the single best accumulated move
        if top_moves_so_far:
            top_move = random.choice(top_moves_so_far)  # random.choice among ties only
            log.info(
                f"[OpponentAI] STEP 8: Executing best accumulated move {top_move} "
                f"(swing: {top_swing_so_far})"
            )
            return top_move

        log.warning("[OpponentAI] STEP 8 FALLBACK: No moves met criteria or time expired. Returning random safe move.")
        return self._get_fallback_move(gs)
