"""
scenes/online_gameplay.py
=========================
OnlineGameplayScene — extends GameplayScene for online 2-player mode.

Key differences from single/local GameplayScene:
  • Input is blocked when it is the remote player's turn or during neutral phases.
  • Every local move is serialised and sent to the relay server.
  • Neutral AI runs only on the Host; the Joiner receives neutral moves via network.
  • Incoming network messages are polled each frame and applied to GameState.
  • A disconnect overlay is shown if the opponent drops, with a 60-second countdown.
    When the countdown expires the remaining player is awarded the win.
  • Pause is disabled; End Game becomes Forfeit (awarding win to the opponent).
  • Clocks are synced after every move: Host always sends timers in phase_sync;
    Joiner applies a gentle correction only when drift exceeds CLOCK_DRIFT_THRESHOLD.
  • Theme, SFX, and music remain entirely local — nothing visual is transmitted.
"""

from __future__ import annotations

import copy
import logging
import math

import pygame

from scenes.base_scene import AppState
from scenes.gameplay import GameplayScene
from network import serialiser
from ui.renderer import pixel_to_board
from record_saver import save_game_record

log = logging.getLogger("KingsTrial.online_gameplay")

# ---------------------------------------------------------------------------
# Overlay palette
# ---------------------------------------------------------------------------
_COL_YOUR_TURN   = (30,  160,  70)
_COL_OPP_TURN    = (180,  90,  20)
_COL_NEUTRAL     = (100,  60, 180)
_COL_DISCONN     = (200,  40,  40)
_COL_OVERLAY_BG  = (0, 0, 0, 150)

# Clock sync: if local and remote timer differ by more than this many seconds,
# apply a gentle blend towards the host's value.
# Using a threshold avoids unnecessary corrections every frame and prevents
# the clocks jumping when there's only minor natural drift.
CLOCK_DRIFT_THRESHOLD = 2.0   # seconds — only correct when drift is noticeable
CLOCK_BLEND_ALPHA     = 0.15  # 15 % remote, 85 % local — gentle, fair blend


class OnlineGameplayScene(GameplayScene):
    """
    Online 2-player gameplay.

    Constructed by app.py after the lobby hands off an `online_session` dict:
        {
            "network_client": NetworkClient,
            "local_color":    "white" | "black",
            "is_host":        bool,
            "room_code":      str,
            "token":          str,
            "config":         GameConfig (hybrid — game settings from host,
                                         visual/audio from local player),
        }
    """

    def __init__(self, online_session: dict, screen: pygame.Surface) -> None:
        cfg = online_session["config"]
        super().__init__(cfg, screen)

        self.network_client = online_session["network_client"]
        self.local_color    = online_session["local_color"]
        self.is_host        = online_session["is_host"]
        self._room_code     = online_session["room_code"]

        # Online-specific UI state
        self._opponent_disconnected    = False
        self._disconnect_timer         = 0.0
        self._disconnect_is_host       = False   # True → clocks freeze for Joiner
        self._room_closed              = False
        self._last_phase_for_sync      = -1      # used to send phase_sync once per turn

        # Skip the pre-game countdown — the lobby already showed a 3-second one.
        self._in_countdown      = False
        self._pregame_countdown = 0.0

        log.info("OnlineGameplayScene init: local=%s is_host=%s room=%s",
                 self.local_color, self.is_host, self._room_code)

    # ------------------------------------------------------------------
    # Scene lifecycle
    # ------------------------------------------------------------------

    def on_enter(self, prev_state=None) -> None:
        log.debug("OnlineGameplayScene entered from %s", prev_state)
        import ui.audio
        ui.audio.play_sound("start")
        # If Host and neutral has first move, kickstart AI
        self._maybe_kickstart_ai()

    # ------------------------------------------------------------------
    # Helpers: online_mode flag + existing move-index from game state
    # ------------------------------------------------------------------

    def _online_mode(self) -> bool:
        """Tell the bottom panel to render online-specific button styles."""
        return True

    def _current_move_index(self) -> int:
        """
        Derive a monotonic move counter from existing GameState fields.
        Uses (cycle-1)*4 + phase_index so no extra tracking variable is needed.
        """
        from constants import PHASE_ORDER
        try:
            phase_idx = PHASE_ORDER.index(self.gs.phase)
        except ValueError:
            phase_idx = 0
        return (self.gs.cycle - 1) * len(PHASE_ORDER) + phase_idx

    # ------------------------------------------------------------------
    # update() — overridden to add network polling + conditional AI
    # ------------------------------------------------------------------

    def update(self, dt: float) -> AppState | None:
        # Always poll network first
        result = self._poll_network()
        if result is not None:
            return result

        if self.gs.game_over:
            return AppState.GAME_OVER

        # Disconnect countdown
        if self._opponent_disconnected:
            self._disconnect_timer -= dt
            if self._disconnect_timer <= 0:
                return self._award_win_after_disconnect()

        # If Host disconnected, Joiner's clocks are frozen
        if self._disconnect_is_host and not self.is_host and self._opponent_disconnected:
            return None

        # Timers
        timed_out = self.gs.update_timers(dt)
        if timed_out:
            self.gs.handle_timeout()
            self._handle_turn_start()

        # Transition delay
        if self.phase_delay_timer > 0:
            self.phase_delay_timer -= dt
            return None

        # AI: neutral turns run on HOST only
        active_owner = self.gs.current_owner()
        if active_owner == "neutral" and self.is_host:
            prev_phase = self.gs.phase
            prev_cycle = self.gs.cycle
            prev_move  = self.ai_move_data
            prev_state = self.ai_state

            self._handle_ai_logic(dt, self.neutral_ai)

            # Detect when AI just executed a valid move (phase or cycle advanced)
            if (prev_state == 4
                    and self.ai_state != 4
                    and (self.gs.phase != prev_phase or self.gs.cycle != prev_cycle)
                    and prev_move):
                self._broadcast_ai_move(prev_move)

        if self.gs.game_over:
            return AppState.GAME_OVER

        return None

    # ------------------------------------------------------------------
    # handle_event() — block Pause keyboard shortcut in online mode
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> AppState | None:
        if event.type == pygame.KEYDOWN:
            # Swallow P key — pausing is not supported in online mode
            if event.key == pygame.K_p:
                return None
            # ESC / Q still exit (game over or disconnect handled elsewhere)
        return super().handle_event(event)

    # ------------------------------------------------------------------
    # _handle_right_click — block on opponent's turn
    # ------------------------------------------------------------------

    def _handle_right_click(self, pos) -> None:
        if self.gs.current_owner() == "neutral":
            return
        if self.gs.current_owner() != self.local_color:
            return
        super()._handle_right_click(pos)

    # ------------------------------------------------------------------
    # _handle_click — override with online input gating + forfeit
    # ------------------------------------------------------------------

    def _handle_click(self, pos) -> AppState | None:
        if self.gs.game_over:
            return None

        mx, my = pos

        # Scrollbar — always works
        if self._sb_track and self._sb_track.collidepoint(mx, my):
            ratio      = (my - self._sb_track.y) / self._sb_track.height
            max_scroll = max(0, len(self.gs.get_move_history()) - 5)
            self.scroll_index = int(ratio * max_scroll)
            return None

        # Pause button is DISABLED in online mode — silently ignore
        if self._pause_btn and self._pause_btn.collidepoint(mx, my):
            return None  # no-op

        # End Game → FORFEIT in online mode
        if self._restart_btn and self._restart_btn.collidepoint(mx, my):
            return self._forfeit_game()

        # Block during neutral AI phase
        active_owner = self.gs.current_owner()
        if active_owner == "neutral":
            return None

        # Block during opponent's turn (core online guard)
        if active_owner != self.local_color:
            return None

        # From here — same as GameplayScene._handle_click but we intercept
        # moves/promotions/respawns to send them over the network.

        # Action buttons
        if hasattr(self, "_action_btns") and self._action_btns:
            for ptype, (action, rect) in self._action_btns.items():
                if rect.collidepoint(mx, my):
                    if action == "respawn":
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
                    else:
                        import ui.audio
                        notation = None
                        sq = self.gs.selected_sq
                        if action == "promote":
                            notation = self.gs.execute_promotion(sq, ptype)
                            if notation:
                                ui.audio.play_sound("promote")
                                self.network_client.send(
                                    serialiser.msg_promote(self._room_code, sq, ptype, "promote"))
                        elif action == "demote":
                            notation = self.gs.execute_demotion(sq, ptype)
                            if notation:
                                ui.audio.play_sound("demote")
                                self.network_client.send(
                                    serialiser.msg_promote(self._room_code, sq, ptype, "demote"))
                        if notation:
                            self.gs.advance_phase()
                            self._handle_turn_start()
                    return None

        # Dialog clicks
        if self.active_dialog:
            for opt_key, (action, rect) in self.dialog_options.items():
                if rect.collidepoint(pos):
                    sq          = self.dialog_sq
                    dialog_type = self.active_dialog
                    self._dispatch_dialog(opt_key, action)
                    self.active_dialog = None
                    self.dialog_sq     = None
                    if dialog_type == "promotion":
                        self.network_client.send(
                            serialiser.msg_promote(self._room_code, sq, opt_key, action))
                    return None
            self.active_dialog = None
            self.dialog_sq     = None
            return None

        # Respawn placement
        if self.respawn_piece_type:
            board_pos = pixel_to_board(*pos)
            if board_pos and board_pos in self.respawn_targets:
                notation = self.gs.execute_respawn(self.respawn_piece_type, board_pos)
                if notation:
                    import ui.audio
                    ui.audio.play_sound("spawn")
                    self.network_client.send(
                        serialiser.msg_respawn(
                            self._room_code, self.respawn_piece_type, board_pos))
                    self.gs.advance_phase()
                    self._handle_turn_start()
            self.respawn_piece_type = None
            self.respawn_targets    = []
            return None

        # Board click
        board_pos = pixel_to_board(*pos)
        if not board_pos:
            return None

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

    # ------------------------------------------------------------------
    # Forfeit — local player gives up, opponent wins
    # ------------------------------------------------------------------

    def _forfeit_game(self) -> AppState:
        """
        Called when the local player clicks FORFEIT.
        Awards the win to the opponent, notifies them via network, saves record.
        """
        winner_color = "black" if self.local_color == "white" else "white"
        self.gs.game_over  = True
        self.gs.status_msg = (
            f"{winner_color.upper()} WINS! "
            f"{self.local_color.capitalize()} forfeited."
        )
        # Notify opponent
        self.network_client.send(
            serialiser.msg_forfeit(self._room_code, self.local_color))

        # Play loss / win sound from local perspective (local player lost)
        import ui.audio
        if winner_color == "white":
            ui.audio.play_sound("white_win")
        else:
            ui.audio.play_sound("black_win")

        self.saved_path = save_game_record(self.gs, self.gs.status_msg, self.config)
        log.info("Local player forfeited. Winner: %s", winner_color)
        return AppState.GAME_OVER

    # ------------------------------------------------------------------
    # Disconnect win award
    # ------------------------------------------------------------------

    def _award_win_after_disconnect(self) -> AppState:
        """
        Called when the reconnect window expires.
        The remaining player (us) wins; record is saved and we go to GAME_OVER.
        """
        winner_color = self.local_color
        loser_color  = "black" if winner_color == "white" else "white"
        self.gs.game_over  = True
        self.gs.status_msg = (
            f"{winner_color.upper()} WINS! "
            f"{loser_color.capitalize()} disconnected."
        )
        self._opponent_disconnected = False
        self._disconnect_timer      = 0.0

        import ui.audio
        if winner_color == "white":
            ui.audio.play_sound("white_win")
        else:
            ui.audio.play_sound("black_win")

        self.saved_path = save_game_record(self.gs, self.gs.status_msg, self.config)
        log.info("Opponent failed to reconnect. %s wins.", winner_color)
        return AppState.GAME_OVER

    # ------------------------------------------------------------------
    # _make_move — send move to relay after applying locally
    # ------------------------------------------------------------------

    def _make_move(self, from_sq: tuple, to_sq: tuple) -> None:
        super()._make_move(from_sq, to_sq)
        # Relay the move to the remote player
        self.network_client.send(
            serialiser.msg_move(self._room_code, from_sq, to_sq))
        # Phase sync (timers always included — host is authoritative)
        self.network_client.send(
            serialiser.msg_phase_sync(self._room_code, self.gs))

    # ------------------------------------------------------------------
    # AI broadcast (neutral moves on Host → send to Joiner)
    # ------------------------------------------------------------------

    def _broadcast_ai_move(self, move_data) -> None:
        """Called right after neutral AI executes a move on the Host."""
        if isinstance(move_data[0], str):
            action = move_data[0]
            if action == "SPAWN":
                self.network_client.send(
                    serialiser.msg_respawn(
                        self._room_code, move_data[1], move_data[2]))
            elif action == "PROMOTE":
                self.network_client.send(
                    serialiser.msg_promote(
                        self._room_code, move_data[1], move_data[2], "promote"))
        else:
            from_sq, to_sq = move_data
            self.network_client.send(
                serialiser.msg_move(self._room_code, from_sq, to_sq))
        # Phase sync (timers always included)
        self.network_client.send(
            serialiser.msg_phase_sync(self._room_code, self.gs))

    # ------------------------------------------------------------------
    # Network polling
    # ------------------------------------------------------------------

    def _poll_network(self) -> AppState | None:
        for msg in self.network_client.poll():
            result = self._handle_net_msg(msg)
            if result is not None:
                return result
        return None

    def _handle_net_msg(self, msg: dict) -> AppState | None:
        mtype = msg.get("type")

        # ── Game-state messages ──────────────────────────────────────
        if mtype in ("move", "promote", "respawn"):
            notation = serialiser.apply_message(msg, self.gs)
            if notation:
                if mtype == "move":
                    self._play_move_sound(notation)
                elif mtype == "promote":
                    import ui.audio
                    action = msg.get("action", "promote")
                    ui.audio.play_sound("promote" if action == "promote" else "demote")
                elif mtype == "respawn":
                    import ui.audio
                    ui.audio.play_sound("spawn")

                self.gs.check_win_conditions()
                if self.gs.game_over:
                    import ui.audio
                    if "White" in self.gs.status_msg:
                        ui.audio.play_sound("white_win")
                    elif "Black" in self.gs.status_msg:
                        ui.audio.play_sound("black_win")
                    self.saved_path = save_game_record(
                        self.gs, self.gs.status_msg, self.config)
                    return AppState.GAME_OVER
                else:
                    self.gs.advance_phase()
                    self._handle_turn_start()
            else:
                log.warning("Remote message produced no notation: %s", msg)

        # ── Phase sync check + threshold-based clock correction ──────
        elif mtype == "phase_sync":
            if not serialiser.check_phase_sync(msg, self.gs):
                log.warning(
                    "PHASE DESYNC detected! remote cycle=%s phase=%s pieces=%s | "
                    "local cycle=%s phase=%s pieces=%s",
                    msg.get("cycle"), msg.get("phase"), msg.get("piece_count"),
                    self.gs.cycle, self.gs.phase, len(self.gs.board),
                )
                # If we are the host, send a full snapshot to resync the joiner
                if self.is_host:
                    self.network_client.send(
                        serialiser.msg_state_snapshot(self._room_code, self.gs))

            # Clock drift correction (Joiner only — Host is the authority)
            # Applied on every phase_sync, but only when drift exceeds threshold.
            if not self.is_host and "timers" in msg:
                remote_timers = msg["timers"]
                for owner in ("white", "black", "neutral"):
                    local_t  = self.gs.timers.get(owner, 0.0)
                    remote_t = remote_timers.get(owner, local_t)
                    drift    = abs(local_t - remote_t)
                    if drift > CLOCK_DRIFT_THRESHOLD:
                        corrected = (1.0 - CLOCK_BLEND_ALPHA) * local_t + CLOCK_BLEND_ALPHA * remote_t
                        log.debug(
                            "Clock correction for %s: local=%.2fs remote=%.2fs "
                            "drift=%.2fs → corrected=%.2fs",
                            owner, local_t, remote_t, drift, corrected
                        )
                        self.gs.timers[owner] = corrected

        # ── State snapshot (Joiner receives from Host to resync) ─────
        elif mtype == "state_snapshot":
            if not self.is_host:
                serialiser.apply_message(msg, self.gs)
                log.info("State snapshot applied from host")

        # ── Forfeit (opponent gave up) ────────────────────────────────
        elif mtype == "forfeit":
            forfeiting_color = msg.get("forfeiting_color", "")
            winner_color = "black" if forfeiting_color == "white" else "white"
            self.gs.game_over  = True
            self.gs.status_msg = (
                f"{winner_color.upper()} WINS! "
                f"{forfeiting_color.capitalize()} forfeited."
            )
            import ui.audio
            if winner_color == "white":
                ui.audio.play_sound("white_win")
            else:
                ui.audio.play_sound("black_win")
            self.saved_path = save_game_record(self.gs, self.gs.status_msg, self.config)
            log.info("Opponent forfeited. %s wins.", winner_color)
            return AppState.GAME_OVER

        # ── Disconnect ───────────────────────────────────────────────
        elif mtype == "opponent_disconnected":
            self._opponent_disconnected = True
            self._disconnect_timer     = float(msg.get("reconnect_window_sec", 60))
            disc_role = msg.get("role", "")
            # If HOST disconnected, Joiner freezes clocks
            self._disconnect_is_host = (disc_role == "host") and not self.is_host
            log.info("Opponent disconnected (role=%s). Reconnect window: %ss",
                     disc_role, self._disconnect_timer)

        elif mtype == "opponent_reconnected":
            self._opponent_disconnected = False
            self._disconnect_timer      = 0.0
            self._disconnect_is_host    = False
            # Host sends a full snapshot so the rejoining Joiner resyncs instantly
            if self.is_host:
                self.network_client.send(
                    serialiser.msg_state_snapshot(self._room_code, self.gs))
            log.info("Opponent reconnected")

        elif mtype == "room_closed":
            # Relay closed the room — if we're still in game, we win by default
            reason = msg.get("reason", "")
            log.info("Room closed: %s", reason)
            if not self.gs.game_over:
                return self._award_win_after_disconnect()

        else:
            log.debug("Unhandled network message type in gameplay: %s", mtype)

        return None

    # ------------------------------------------------------------------
    # render() — parent + online overlays
    # ------------------------------------------------------------------

    def render(self, screen: pygame.Surface) -> None:
        super().render(screen)
        self._render_online_overlays(screen)

    def _render_online_overlays(self, screen: pygame.Surface) -> None:
        W, H = screen.get_size()
        font_banner = pygame.font.SysFont("dejavusansmono", 15, bold=True)
        font_modal  = pygame.font.SysFont("dejavusansmono", 22, bold=True)
        font_sub    = pygame.font.SysFont("dejavusansmono", 16)

        # ── Turn banner (top-right corner) ───────────────────────────
        owner = self.gs.current_owner()
        if self.gs.game_over:
            pass  # don't show banner when game is over
        elif owner == "neutral":
            banner_color = _COL_NEUTRAL
            banner_text  = "NEUTRAL  ·  AI"
        elif owner == self.local_color:
            banner_color = _COL_YOUR_TURN
            banner_text  = "YOUR TURN"
        else:
            banner_color = _COL_OPP_TURN
            banner_text  = "OPPONENT'S TURN"

        if not self.gs.game_over:
            s    = font_banner.render(banner_text, True, (255, 255, 255))
            pad  = 8
            bw   = s.get_width() + pad * 2
            bh   = s.get_height() + pad
            brect = pygame.Rect(W - bw - 8, 6, bw, bh)
            pygame.draw.rect(screen, banner_color, brect, border_radius=5)
            screen.blit(s, (brect.x + pad, brect.y + pad // 2))

            # Room code hint (bottom of banner)
            rc_s = font_sub.render(f"Room: {self._room_code}", True, (150, 155, 170))
            screen.blit(rc_s, rc_s.get_rect(topright=(W - 8, brect.bottom + 4)))

        # ── Disconnect overlay ───────────────────────────────────────
        if self._opponent_disconnected:
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill(_COL_OVERLAY_BG)
            screen.blit(ov, (0, 0))

            panel_w, panel_h = 500, 155
            pr = pygame.Rect(0, 0, panel_w, panel_h)
            pr.center = (W // 2, H // 2)
            pygame.draw.rect(screen, (20, 20, 30), pr, border_radius=12)
            pygame.draw.rect(screen, _COL_DISCONN, pr, width=2, border_radius=12)

            if self._disconnect_is_host:
                title = "HOST DISCONNECTED"
                sub   = (f"Game paused. Waiting for host to reconnect…  "
                         f"({int(self._disconnect_timer)}s)")
            else:
                title = "OPPONENT DISCONNECTED"
                sub   = (f"Waiting for opponent to reconnect…  "
                         f"({int(self._disconnect_timer)}s)")

            ts = font_modal.render(title, True, (255, 90, 90))
            ss = font_sub.render(sub,   True, (200, 200, 210))
            win_note = font_sub.render(
                "You will be awarded the win if they do not return in time.",
                True, (160, 210, 160))
            screen.blit(ts, ts.get_rect(center=(W // 2, H // 2 - 35)))
            screen.blit(ss, ss.get_rect(center=(W // 2, H // 2 + 8)))
            screen.blit(win_note, win_note.get_rect(center=(W // 2, H // 2 + 36)))

        # ── Room closed overlay ──────────────────────────────────────
        if self._room_closed:
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 200))
            screen.blit(ov, (0, 0))

            ts = font_modal.render("CONNECTION LOST  —  Game Ended", True, (255, 100, 100))
            ss = font_sub.render(
                "Press ESC to return to the main menu.", True, (200, 200, 210))
            screen.blit(ts, ts.get_rect(center=(W // 2, H // 2 - 20)))
            screen.blit(ss, ss.get_rect(center=(W // 2, H // 2 + 20)))

    # ------------------------------------------------------------------
    # Clean up on exit
    # ------------------------------------------------------------------

    def on_exit(self) -> None:
        super().on_exit()
        # Disconnect cleanly; lobby already handed ownership to us
        if self.network_client:
            self.network_client.disconnect()
