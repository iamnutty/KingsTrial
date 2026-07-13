"""
scenes/gameplay.py
==================
GameplayScene — the main in-game screen.

Extracted from KingsTrialApp in the old main.py. Contains all
board interaction logic: selection, movement, AI, dialogs, rendering.

Returns AppState signals on:
    PAUSED          → P key / Pause button
    GAME_OVER       → win condition triggered
"""

from __future__ import annotations
import os
import logging
import pygame
import concurrent.futures

from scenes.base_scene import Scene, AppState
from config import GameConfig
from game_state import GameState
from layout_reader import load_board_state
from move_validator import get_legal_moves
from record_saver import save_game_record
from ai.opponent_ai import OpponentAI
from ai.neutral_ai import NeutralAI
import constants as C
from ui.renderer  import draw_board, draw_rank_file_labels, draw_pieces, draw_highlights, pixel_to_board
from ui.panels    import draw_backgrounds, draw_top_bar, draw_bottom_panel
from ui.dialogs   import draw_promotion_dialog, draw_respawn_panel

log = logging.getLogger("KingsTrial.gameplay")


def _load_initial_pieces(layout_file: str) -> list[dict]:
    try:
        import ui.theme
        assets_dir = getattr(ui.theme.manager, "assets_dir", "assets")
        path = os.path.join(assets_dir, "maps", layout_file)
        pieces = load_board_state(path)
        log.info("Loaded %d pieces from %s", len(pieces), layout_file)
        return pieces
    except Exception as exc:
        log.warning("Could not load %s (%s). Using fallback.", layout_file, exc)
        return [
            {"rank": 4,  "col": 5, "type": "K", "owner": "white"},
            {"rank": 23, "col": 4, "type": "K", "owner": "black"},
        ]


def _map_ai_config(level_str: str) -> tuple[int, int]:
    """Map UI string to (elo, depth). Defaults to Medium 1500."""
    # Stockfish 16.1+ enforces a strict minimum UCI_Elo of 1320.
    mapping = {
        "random": (1320,  1), # Minimum legal ELO
        "easy":   (1320,  5),
        "medium": (1710, 10),
        "hard":   (2100, 15),
    }
    return mapping.get(level_str.lower(), (1710, 10))

class GameplayScene(Scene):
    """Active gameplay scene."""

    def __init__(self, config: GameConfig, screen: pygame.Surface) -> None:
        self.config = config
        self.screen = screen

        self._initial_pieces = _load_initial_pieces(config.layout_file)
        self.gs = GameState(self._initial_pieces, time_control=config.time_control)

        # ── AI ───────────────────────────────────────────────────────────
        # Note: We instantiate persistent Stockfish sessions here for the game duration.
        # This avoids the overhead of opening/closing the engine process per evaluation.
        # Crash recovery is handled inside each AI's choose_move() function.
        elo, depth = _map_ai_config(self.config.neutral_ai)
        self.neutral_ai  = NeutralAI(elo=elo, depth=depth, difficulty=self.config.neutral_ai.lower())
        
        # Single Player setup
        self.opponent_ai = None
        self.human_color = "white"
        
        if self.config.single_player:
            opp_elo, opp_depth = _map_ai_config(self.config.opponent_ai)
            self.opponent_ai = OpponentAI(elo=opp_elo, depth=opp_depth, difficulty=self.config.opponent_ai.lower())
            
            hc = self.config.human_colour.lower()
            if hc == "random":
                import random
                self.human_color = random.choice(["white", "black"])
            else:
                self.human_color = hc
            log.info("Single Player Mode initialized. Human: %s | Opponent: %s", self.human_color, self.config.opponent_ai)

        # ── UI state ─────────────────────────────────────────────────────
        self.scroll_index  = 0
        self.active_dialog = None      # 'promotion' | 'respawn'
        self.dialog_sq     = None
        self.dialog_options: dict = {}

        # Respawn placement
        self.respawn_piece_type = None
        self.respawn_targets    = []

        # AI animation state machine
        self.ai_state      = 0   # 0=idle 1=thinking 2=selecting 3=highlighting 4=executing
        self.ai_timer      = 0.0
        self.ai_move_data  = None

        # Turn-change delay
        self.phase_delay_timer = 0.0

        # Pre-game orientation countdown (shown before any input is accepted)
        # Set to True only on a fresh game start; overridden to False by online mode
        # (lobby countdown already handled orientation there).
        self._in_countdown      = False
        self._pregame_countdown = 5.0

        # Game record
        self.saved_path: str | None = None

        # Cached button rects (set on each render)
        self._pause_btn   = None
        self._restart_btn = None
        self._sb_track    = None
        self._action_btns = {}

        # ARCH-002: Executor and future are lifecycle-managed via _shutdown_executor().
        # Initialised here so reset() and on_exit() can always safely call shutdown.
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._ai_future: concurrent.futures.Future | None = None

    # ── Scene lifecycle ───────────────────────────────────────────────────

    def on_enter(self, prev_state: AppState | None = None) -> None:
        log.debug("GameplayScene entered from %s", prev_state)
        # Start fresh-game countdown when entering from MENU, CONFIRM_RESTART, or cold start.
        # Do NOT restart countdown when returning from PAUSED, SAVE_GAME, etc.
        if prev_state in (AppState.MENU, AppState.CONFIRM_RESTART, None):
            self._in_countdown      = True
            self._pregame_countdown = 5.0
            import ui.audio
            ui.audio.play_sound("start")
        else:
            # e.g. returning from PAUSED, LOAD_GAME — no new countdown
            pass

    def on_exit(self) -> None:
        """ARCH-002: Cleanly shut down any in-flight AI computation when leaving gameplay."""
        self._shutdown_executor()

    def _maybe_kickstart_ai(self) -> None:
        """
        Prime the AI state machine at game start or after a reset.
        Only triggers if the current turn belongs to an AI (neutral or opponent).
        Without this, ai_state stays at 0 and _handle_ai_logic never fires on
        the very first frame, causing the AI to drain its entire clock doing nothing.
        """
        owner = self.gs.current_owner()
        is_ai_turn = (
            owner == "neutral"
            or (self.config.single_player and owner != self.human_color)
        )
        if is_ai_turn:
            self._handle_turn_start()
            log.info("[GameplayScene] Kickstarted AI for opening turn (owner=%s)", owner)

    # ── Scene interface ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> AppState | None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_q, pygame.K_ESCAPE):
                return AppState.QUIT

            elif event.key == pygame.K_p:
                return AppState.PAUSED

            elif event.key == pygame.K_s and self.gs.game_over:
                path = save_game_record(self.gs, self.gs.status_msg, self.config)
                self.saved_path = path
                log.info("Manual save: %s", path)

            elif event.key == pygame.K_t:  # debug: advance phase
                self.gs.advance_phase()
                log.debug("Phase advanced manually → %s", C.PHASE_NAMES[self.gs.phase])

        elif event.type == pygame.MOUSEWHEEL:
            self.scroll_index += event.y
            history_len  = len(self.gs.get_move_history())
            max_scroll   = max(0, history_len - 5)
            self.scroll_index = max(0, min(self.scroll_index, max_scroll))

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                return self._handle_click(event.pos)
            elif event.button == 3:
                self._handle_right_click(event.pos)

        return None

    def update(self, dt: float) -> AppState | None:
        # Pre-game countdown: block all AI and input until it finishes
        if self._in_countdown:
            self._pregame_countdown -= dt
            if self._pregame_countdown <= 0:
                self._in_countdown = False
                self._maybe_kickstart_ai()  # prime AI now that play begins
            return None

        if self.gs.game_over:
            return AppState.GAME_OVER

        # Timer
        timed_out = self.gs.update_timers(dt)
        if timed_out:
            self.gs.handle_timeout()
            self._handle_turn_start()

        # Transition delay
        if self.phase_delay_timer > 0:
            self.phase_delay_timer -= dt
            return None

        # AI Turn Handling
        # If it's a Neutral Phase, neutral_ai always plays.
        # If Single Player is ON, and it's a Player Phase but not the human's color, opponent_ai plays.
        
        active_owner = self.gs.current_owner()
        
        if active_owner == "neutral":
            self._handle_ai_logic(dt, self.neutral_ai)
        elif self.config.single_player and active_owner != self.human_color:
            self._handle_ai_logic(dt, self.opponent_ai)

        if self.gs.game_over:
            return AppState.GAME_OVER

        return None

    def render(self, screen: pygame.Surface) -> None:
        draw_backgrounds(screen)
        draw_board(screen, self.gs)
        draw_rank_file_labels(screen)
        
        draw_pieces(screen, self.gs.all_pieces())

        active_hl = self.gs.legal_targets if not self.respawn_piece_type else self.respawn_targets
        
        # Determine the owning team for the highlight colour
        hl_owner = None
        if self.gs.selected_sq:
            piece = self.gs.get(*self.gs.selected_sq)
            if piece:
                hl_owner = piece["owner"]
        elif self.respawn_piece_type:
            hl_owner = self.gs.current_owner()

        draw_highlights(screen, self.gs.selected_sq, hl_owner, active_hl)

        # BUG-002 FIX: update_timers() is a state-mutating call and must not be
        # inside render(). Timers are already advanced correctly in update(dt).
        # The values read by draw_top_bar() below are always current.
        draw_top_bar(
            screen,
            white_time   = self.gs.timers["white"],
            neutral_time = self.gs.timers["neutral"],
            black_time   = self.gs.timers["black"],
            white_score  = self.gs.points["white"],
            black_score  = self.gs.points["black"],
            active_phase = self.gs.phase,
        )

        self._pause_btn, self._restart_btn, self._sb_track, self._action_btns = draw_bottom_panel(
            screen,
            move_log        = self.gs.get_move_history(),
            current_phase   = self.gs.phase,
            move_number     = self.gs.cycle,
            game_status_msg = self.gs.status_msg,
            paused          = False,
            scroll_index    = self.scroll_index,
            selected_piece  = self.gs.get(*self.gs.selected_sq) if self.gs.selected_sq else None,
            player_points   = self.gs.points.get(self.gs.current_owner(), 0),
            respawn_pool    = self.gs.respawn_pool.get(self.gs.current_owner(), []),
            owner           = self.gs.current_owner(),
            piece_counts    = self.gs.get_piece_counts(self.gs.current_owner()),
            online_mode     = self._online_mode(),
        )

        pygame.display.set_caption(
            f"King's Trial  ♟  {C.PHASE_NAMES[self.gs.phase]}  |  Cycle {self.gs.cycle}"
        )

        # Dialogs
        if self.active_dialog == 'promotion' and self.dialog_sq:
            piece = self.gs.get(*self.dialog_sq)
            ctype = piece["type"] if piece else None
            owner = self.gs.current_owner()
            self.dialog_options = draw_promotion_dialog(
                screen, self.dialog_sq,
                self.gs.points[owner],
                owner,
                current_type=ctype,
                piece_counts=self.gs.get_piece_counts(owner)
            )
        elif self.active_dialog == 'respawn' and self.dialog_sq:
            owner     = self.gs.current_owner()
            clickable = draw_respawn_panel(
                screen, self.dialog_sq,
                self.gs.points[owner],
                self.gs.respawn_pool[owner],
                owner,
                piece_counts=self.gs.get_piece_counts(owner)
            )
            self.dialog_options = {p["type"]: ("respawn", rect) for p, rect in clickable}

        # Pre-game countdown overlay
        if self._in_countdown:
            self._render_pregame_countdown(screen)

    def _online_mode(self) -> bool:
        """Subclasses override to True so the correct button styles are rendered."""
        return False

    def _render_pregame_countdown(self, screen: pygame.Surface) -> None:
        """Full-screen semi-transparent countdown overlay (3 → 1)."""
        import math
        W, H = screen.get_size()
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        screen.blit(ov, (0, 0))

        remaining = max(0.0, self._pregame_countdown)
        number    = max(1, int(math.ceil(remaining)))
        pulse     = 1.0 + 0.12 * math.sin(remaining * 8)

        font_big = pygame.font.SysFont("dejavusansmono", 90, bold=True)
        font_sub = pygame.font.SysFont("dejavusansmono", 22, bold=True)

        n_surf  = font_big.render(str(number), True, (255, 200, 50))
        scaled  = pygame.transform.rotozoom(n_surf, 0, pulse)
        screen.blit(scaled, scaled.get_rect(center=(W // 2, H // 2 - 20)))

        go = font_sub.render("Game starting …", True, (210, 215, 230))
        screen.blit(go, go.get_rect(center=(W // 2, H // 2 + 65)))

    # ── Internal helpers ──────────────────────────────────────────────────

    def _handle_click(self, pos: tuple[int, int]) -> AppState | None:
        if self.gs.game_over:
            return None

        mx, my = pos

        # Scrollbar
        if self._sb_track and self._sb_track.collidepoint(mx, my):
            # BUG-007 FIX: ratio goes 0.0 (top) → 1.0 (bottom), matching standard
            # scrollbar UX where top = beginning of log, bottom = end.
            ratio        = (my - self._sb_track.y) / self._sb_track.height
            max_scroll   = max(0, len(self.gs.get_move_history()) - 5)
            self.scroll_index = int(ratio * max_scroll)
            return None

        # Menu buttons
        if self._pause_btn and self._pause_btn.collidepoint(mx, my):
            return AppState.PAUSED
        if self._restart_btn and self._restart_btn.collidepoint(mx, my):
            return AppState.CONFIRM_RESTART

        # Block human input if it's currently an AI's turn
        active_owner = self.gs.current_owner()
        if active_owner == "neutral":
            return None
        if self.config.single_player and active_owner != self.human_color:
            return None

        # Action buttons check
        if hasattr(self, '_action_btns') and self._action_btns:
            for ptype, (action, rect) in self._action_btns.items():
                if rect.collidepoint(mx, my):
                    if action == 'respawn':
                        import ui.audio
                        ui.audio.play_sound("select")
                        self.respawn_piece_type = ptype
                        kr, kc = self.gs.selected_sq
                        self.respawn_targets = [
                            (kr + dr, kc + dc)
                            for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                            if (dr, dc) != (0, 0)
                            and self.gs.min_playable_rank <= kr + dr <= self.gs.max_playable_rank
                            and 1 <= kc + dc <= 8
                            and (kr + dr, kc + dc) not in self.gs.board
                        ]
                        log.debug("Respawn mode via button: %s, targets=%d", ptype, len(self.respawn_targets))
                    else:
                        import ui.audio
                        # BUG-005 FIX: Initialise notation to None so the check
                        # below is safe even if action is an unexpected value.
                        notation = None
                        if action == 'promote':
                            notation = self.gs.execute_promotion(self.gs.selected_sq, ptype)
                            if notation: ui.audio.play_sound("promote")
                        elif action == 'demote':
                            notation = self.gs.execute_demotion(self.gs.selected_sq, ptype)
                            if notation: ui.audio.play_sound("demote")
                        if notation:
                            self.gs.advance_phase()
                            self._handle_turn_start()
                    return None

        # Dialog clicks
        if self.active_dialog:
            for opt_key, (action, rect) in self.dialog_options.items():
                if rect.collidepoint(pos):
                    self._dispatch_dialog(opt_key, action)
                    self.active_dialog = None
                    self.dialog_sq     = None
                    return None
            self.active_dialog = None
            self.dialog_sq     = None
            return None

        # Respawn placement
        if self.respawn_piece_type:
            board_pos = pixel_to_board(*pos)
            if board_pos in self.respawn_targets:
                notation = self.gs.execute_respawn(self.respawn_piece_type, board_pos)
                if notation:
                    import ui.audio
                    ui.audio.play_sound("spawn")
                    self.gs.advance_phase()
                    self._handle_turn_start()
            self.respawn_piece_type = None
            self.respawn_targets    = []
            return None

        # Scrollbar and Menu buttons handled at the start of _handle_click

        # Board
        board_pos = pixel_to_board(*pos)
        if not board_pos:
            return None
        


        rank, col = board_pos
        log.debug("Click at board %s (File %s%d)", board_pos, "ABCDEFGH"[col - 1], rank)

        if self.gs.selected_sq:
            if board_pos in self.gs.legal_targets:
                self._make_move(self.gs.selected_sq, board_pos)
                if self.gs.game_over:
                    return AppState.GAME_OVER
            else:
                self._select_square(board_pos)
        else:
            self._select_square(board_pos)

        return None

    def _dispatch_dialog(self, opt_key: str, action: str) -> None:
        if self.active_dialog == 'promotion':
            import ui.audio
            # BUG-006 FIX: Initialise notation defensively; both branches of the
            # if/else below assign it, but this guard prevents UnboundLocalError
            # if future code paths skip the assignment.
            notation = None
            if action == 'promote':
                notation = self.gs.execute_promotion(self.dialog_sq, opt_key)
                if notation: ui.audio.play_sound("promote")
            else:
                notation = self.gs.execute_demotion(self.dialog_sq, opt_key)
                if notation: ui.audio.play_sound("demote")

            if notation:
                self.gs.advance_phase()
                self._handle_turn_start()

        elif self.active_dialog == 'respawn':
            # Enter placement mode
            self.respawn_piece_type = opt_key
            kr, kc = self.dialog_sq
            self.respawn_targets = [
                (kr + dr, kc + dc)
                for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                if (dr, dc) != (0, 0)
                and self.gs.min_playable_rank <= kr + dr <= self.gs.max_playable_rank
                and 1 <= kc + dc <= 8
                and (kr + dr, kc + dc) not in self.gs.board
            ]
            log.debug("Respawn mode: %s, targets=%d", opt_key, len(self.respawn_targets))

    def _handle_right_click(self, pos: tuple[int, int]) -> None:
        if self.gs.game_over:
            return

        if self.active_dialog or self.respawn_piece_type:
            self.active_dialog = None
            self.dialog_sq     = None
            self.respawn_piece_type = None
            self.respawn_targets    = []
            return

        # Block human input if it's the Opponent AI's turn
        if self.config.single_player and self.gs.current_owner() != self.human_color:
            return

        board_pos = pixel_to_board(*pos)
        if not board_pos:
            return
        piece = self.gs.get(*board_pos)
        if not piece or piece["owner"] != self.gs.current_owner():
            return

        if piece["type"] != "K":
            self.active_dialog = 'promotion'
            self.dialog_sq     = board_pos
            log.debug("Promotion dialog: %s %s at %s", piece["owner"], piece["type"], board_pos)
        else:
            self.active_dialog = 'respawn'
            self.dialog_sq     = board_pos
            log.debug("Respawn panel: %s at %s", piece["owner"], board_pos)

    def _select_square(self, sq: tuple[int, int]) -> None:
        piece = self.gs.get(*sq)
        if piece and piece["owner"] == self.gs.current_owner():
            import ui.audio
            ui.audio.play_sound("select")
            
            self.gs.selected_sq    = sq
            self.gs.legal_targets  = get_legal_moves(sq, self.gs)
            log.debug("Selected %s %s at %s. Moves: %d", piece["owner"], piece["type"], sq, len(self.gs.legal_targets))
        else:
            self.gs.selected_sq   = None
            self.gs.legal_targets = []

    def _make_move(self, from_sq: tuple, to_sq: tuple) -> None:
        notation = self.gs.execute_move(from_sq, to_sq)
        if notation:
            self._play_move_sound(notation)
            self.gs.check_win_conditions()
            if not self.gs.game_over:
                self.gs.advance_phase()
                self._handle_turn_start()
            else:
                import ui.audio
                if "White" in self.gs.status_msg:
                    ui.audio.play_sound("white_win")
                elif "Black" in self.gs.status_msg:
                    ui.audio.play_sound("black_win")
                self.saved_path = save_game_record(self.gs, self.gs.status_msg, self.config)
                log.info("Game over. Saved to: %s", self.saved_path)

    def _play_move_sound(self, notation: str) -> None:
        import ui.audio
        if "x" in notation:
            ui.audio.play_sound("capture")
        else:
            ui.audio.play_sound("move")

    def _handle_turn_start(self) -> None:
        self.scroll_index       = 0
        self.active_dialog      = None
        self.respawn_piece_type = None
        self.respawn_targets    = []
        self.ai_state           = 1
        self.ai_timer           = 0.0
        self.ai_move_data       = None
        self.phase_delay_timer  = 0.5

    def _shutdown_executor(self) -> None:
        """ARCH-002: Cleanly stop any in-flight AI computation.

        cancel_futures=True cancels pending (not-yet-started) futures.
        An already-running Stockfish call will complete in the background,
        but its result is discarded because _ai_future is cleared here.
        """
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        self._ai_future = None

    def quit_ais(self) -> None:
        """Cleanly terminate Stockfish engine processes when discarding this scene or resetting."""
        if hasattr(self, 'neutral_ai') and self.neutral_ai:
            self.neutral_ai.quit()
        if hasattr(self, 'opponent_ai') and self.opponent_ai:
            self.opponent_ai.quit()

    def _handle_ai_logic(self, dt: float, engine) -> None:
        self.ai_timer += dt
        if self.ai_state == 1:   # thinking
            if self.ai_timer >= 0.5:
                # Dispatch Stockfish to a background thread to prevent Pygame from freezing
                if self._ai_future is None:
                    if self._executor is None:
                        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    self._ai_future = self._executor.submit(engine.choose_move, self.gs)
                
                if self._ai_future.done():
                    self.ai_move_data = self._ai_future.result()
                    self._ai_future = None
                    if not self.ai_move_data:
                        # No legal moves, skip turn (Stockfish is mated or trapped)
                        self.gs.advance_phase()
                        self._handle_turn_start()
                    else:
                        self.ai_state, self.ai_timer = 2, 0.0
                        import ui.audio
                        ui.audio.play_sound("select")

        elif self.ai_state == 2:  # selecting
            if isinstance(self.ai_move_data[0], str):
                action = self.ai_move_data[0]
                self.gs.selected_sq = self.ai_move_data[2] if action == "SPAWN" else self.ai_move_data[1]
                self.gs.legal_targets = [self.gs.selected_sq]
            else:
                self.gs.selected_sq = self.ai_move_data[0]
                self.gs.legal_targets = get_legal_moves(self.gs.selected_sq, self.gs)
                
            if self.ai_timer >= C.AI_MOVE_DELAY_SECONDS:
                self.ai_state, self.ai_timer = 3, 0.0

        elif self.ai_state == 3:  # highlighting
            if not isinstance(self.ai_move_data[0], str):
                self.gs.legal_targets = [self.ai_move_data[1]]
                
            if self.ai_timer >= C.AI_MOVE_DELAY_SECONDS:
                self.ai_state, self.ai_timer = 4, 0.0

        elif self.ai_state == 4:  # executing
            if isinstance(self.ai_move_data[0], str):
                action = self.ai_move_data[0]
                if action == "SPAWN":
                    notation = self.gs.execute_respawn(self.ai_move_data[1], self.ai_move_data[2])
                elif action == "PROMOTE":
                    notation = self.gs.execute_promotion(self.ai_move_data[1], self.ai_move_data[2])
                else:
                    notation = None
            else:
                from_sq, to_sq = self.ai_move_data
                notation = self.gs.execute_move(from_sq, to_sq)
                
            if notation:
                if isinstance(self.ai_move_data[0], str):
                    import ui.audio
                    if self.ai_move_data[0] == "SPAWN":
                        ui.audio.play_sound("spawn")
                    else:
                        ui.audio.play_sound("promote")
                else:
                    self._play_move_sound(notation)
                    
                self.gs.check_win_conditions()
                if self.gs.game_over:
                    import ui.audio
                    # BUG-001 FIX: 'utils' module does not exist. save_game_record
                    # is already imported at the top of this file from record_saver.
                    if "White" in self.gs.status_msg:
                        ui.audio.play_sound("white_win")
                    elif "Black" in self.gs.status_msg:
                        ui.audio.play_sound("black_win")
                    self.saved_path = save_game_record(self.gs, self.gs.status_msg, self.config)
                    log.info("Game over. Saved to: %s", self.saved_path)
                    
            else:
                log.error(f"AI attempted invalid move: {self.ai_move_data}")
                    
            self.gs.selected_sq   = None
            self.gs.legal_targets = []
            
            if not self.gs.game_over:
                self.gs.advance_phase()
                self._handle_turn_start()

    def reset(self) -> None:
        """Reset to initial board state (called after Confirm Restart)."""
        # ARCH-002: Shut down any in-flight AI computation before replacing GameState.
        # This prevents the old Stockfish thread from operating on the new gs object.
        self._shutdown_executor()
        self.quit_ais()

        self.gs = GameState(self._initial_pieces, time_control=self.config.time_control)

        # Re-apply AI configurations in case they changed in Settings
        elo, depth = _map_ai_config(self.config.neutral_ai)
        self.neutral_ai  = NeutralAI(elo=elo, depth=depth, difficulty=self.config.neutral_ai.lower())

        self.opponent_ai = None
        # Default to "white" for both single-player and 2-player modes.
        # In 2-player mode, human_color is not read by input guards (they check
        # config.single_player first), so "white" is a safe sentinel value.
        self.human_color = "white"

        if self.config.single_player:
            opp_elo, opp_depth = _map_ai_config(self.config.opponent_ai)
            self.opponent_ai = OpponentAI(elo=opp_elo, depth=opp_depth, difficulty=self.config.opponent_ai.lower())

            hc = self.config.human_colour.lower()
            if hc == "random":
                import random
                self.human_color = random.choice(["white", "black"])
            else:
                self.human_color = hc
            log.info("Resetting Game: Human: %s | Opponent: %s", self.human_color, self.config.opponent_ai)
        # ARCH-003 FIX: Removed `else: self.human_color = None` which blocked ALL
        # human input in 2-player mode after a reset (None matched neither colour).

        self.scroll_index       = 0
        self.active_dialog      = None
        self.dialog_sq          = None
        self.dialog_options     = {}
        self.respawn_piece_type = None
        self.respawn_targets    = []
        self.ai_state           = 0
        self.ai_timer           = 0.0
        self.ai_move_data       = None
        self.phase_delay_timer  = 0.0
        self.saved_path         = None
        log.info("GameplayScene reset")
        self._maybe_kickstart_ai()  # Only prime AI if it owns the opening turn
