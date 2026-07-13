"""
scenes/online_lobby.py
======================
OnlineLobbyScene — Play over Web setup screen.

Manages the full pre-game flow for online multiplayer:

  Mode Select
    ├─ HOST  → host_connecting → host_waiting → host_color_select
    │                                                  ↓
    │                                           host_ready_wait → countdown
    └─ JOIN  → join_input → join_connecting → join_waiting_color
                                                       ↓
                                               join_ready_wait → countdown

On countdown completion, sets app.online_session and returns
AppState.ONLINE_GAMEPLAY so app.py can build OnlineGameplayScene.
"""

from __future__ import annotations

import logging
import math
import random
import string
import uuid

import pygame

from scenes.base_scene import Scene, AppState
import constants as C

log = logging.getLogger("KingsTrial.online_lobby")

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
_BG_DARK   = (12, 14, 22)
_PANEL     = (22, 26, 40)
_PANEL2    = (28, 33, 52)
_GOLD      = (255, 200, 50)
_BLUE      = (50, 140, 255)
_GREEN     = (50, 210, 100)
_RED       = (230, 70, 60)
_WHITE_COL = (220, 220, 255)
_BLACK_COL = (80, 90, 110)
_AMBER     = (230, 160, 40)
_TEXT      = (210, 215, 230)
_MUTED     = (110, 120, 145)
_BORDER    = (50, 60, 90)

_FONT_BIG  = None
_FONT_MED  = None
_FONT_SM   = None
_FONT_MONO = None


def _fonts():
    global _FONT_BIG, _FONT_MED, _FONT_SM, _FONT_MONO
    if _FONT_BIG is None:
        _FONT_BIG  = pygame.font.SysFont(["consolas", "arial", "dejavusansmono"], 38, bold=True)
        _FONT_MED  = pygame.font.SysFont(["consolas", "arial", "dejavusansmono"], 22, bold=True)
        _FONT_SM   = pygame.font.SysFont(["consolas", "arial", "dejavusansmono"], 17)
        _FONT_MONO = pygame.font.SysFont(["consolas", "couriernew", "dejavusansmono"], 48, bold=True)


def _gen_room_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=6))


# ---------------------------------------------------------------------------
# Sub-screen identifiers
# ---------------------------------------------------------------------------
_S_MODE_SELECT       = "mode_select"
_S_HOST_CONNECTING   = "host_connecting"
_S_HOST_WAITING      = "host_waiting"       # waiting for opponent to join
_S_HOST_COLOR_SELECT = "host_color_select"  # opponent joined, host picks colour
_S_HOST_READY_WAIT   = "host_ready_wait"    # host clicked ready, waiting for joiner
_S_JOIN_INPUT        = "join_input"
_S_JOIN_CONNECTING   = "join_connecting"
_S_JOIN_WAITING_COL  = "join_waiting_color" # connected, waiting for host colour
_S_JOIN_READY_WAIT   = "join_ready_wait"    # joiner clicked ready
_S_COUNTDOWN         = "countdown"
_S_ERROR             = "error"


class OnlineLobbyScene(Scene):
    """
    Handles the complete pre-game lobby flow for online play.
    Stores result in app.online_session before returning ONLINE_GAMEPLAY.
    """

    def __init__(self, app, screen: pygame.Surface) -> None:
        self.app    = app
        self.screen = screen
        self.config = app.config

        self._sub   = _S_MODE_SELECT
        self._time  = 0.0

        # Shared network state
        self._net_client  = None       # NetworkClient instance
        self._room_code   = ""
        self._token       = ""
        self._role        = ""         # "host" | "joiner"
        self._host_color  = "white"    # chosen by host
        self._local_color = ""         # our colour — empty until assigned
        self._session_cfg = {}

        # Lobby-specific tracking
        self._joiner_ready = False
        self._host_ready   = False

        # Text input (join screen)
        self._input_text   = ""
        self._cursor_blink = 0.0
        self._cursor_vis   = True

        # Error message
        self._error_msg = ""

        # Countdown (0 → 3, displayed as 3-int → 0)
        self._countdown     = 0.0
        self._COUNTDOWN_SEC = 5.0

        # Spinner animation
        self._spinner_angle = 0.0

        # Button rects (set during render)
        self._btn_host  = None
        self._btn_join  = None
        self._btn_white = None
        self._btn_black = None
        self._btn_ready = None
        self._btn_connect = None
        self._btn_back  = None
        self._btn_use_last = None  # clickable hint on join screen

        # Background image (reuse menu bg if available)
        import os
        import ui.theme
        assets_dir = getattr(ui.theme.manager, "assets_dir", None)
        if assets_dir:
            bg_path = os.path.join(assets_dir, "menu_bg.png")
        else:
            bg_path = os.path.join(os.path.dirname(__file__), "..", "assets", "menu_bg.png")
        try:
            self._bg = pygame.image.load(bg_path).convert()
        except Exception:
            self._bg = None
        self._bg_scaled = None
        self._bg_size   = (0, 0)

    # ------------------------------------------------------------------
    # Scene lifecycle
    # ------------------------------------------------------------------

    def on_enter(self, prev_state=None) -> None:
        log.debug("OnlineLobbyScene entered")
        pygame.display.set_caption("King's Trial  ♟  Play over Web")
        self._reset()

    def on_exit(self) -> None:
        # NetworkClient stays alive — it's passed to OnlineGameplayScene
        pass

    def _reset(self) -> None:
        self._sub = _S_MODE_SELECT
        self._net_client  = None
        self._room_code   = ""
        self._token       = ""
        self._role        = ""
        self._host_color  = "white"
        self._local_color = ""    # empty until host assigns
        self._session_cfg = {}
        self._joiner_ready = False
        self._host_ready   = False
        # Pre-fill with last used room code so players can rejoin quickly
        self._input_text   = self.config.last_room_code
        self._error_msg    = ""
        self._countdown    = 0.0

    # ------------------------------------------------------------------
    # Scene interface
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> AppState | None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                if self._sub == _S_MODE_SELECT:
                    return AppState.MENU
                else:
                    self._go_back()
                    return None

            if self._sub == _S_JOIN_INPUT:
                self._handle_text_input(event)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self._handle_click(event.pos)

        return None

    def update(self, dt: float) -> AppState | None:
        self._time        += dt
        self._spinner_angle = (self._spinner_angle + dt * 180) % 360
        self._cursor_blink += dt
        if self._cursor_blink > 0.5:
            self._cursor_blink = 0.0
            self._cursor_vis = not self._cursor_vis

        # Poll network
        if self._net_client:
            for msg in self._net_client.poll():
                result = self._handle_net_msg(msg)
                if result is not None:
                    return result

            # Check for connection errors
            if self._net_client.status == "error":
                self._error_msg = f"Connection error: {self._net_client.error}"
                self._sub = _S_ERROR

        # Countdown
        if self._sub == _S_COUNTDOWN:
            self._countdown += dt
            if self._countdown >= self._COUNTDOWN_SEC:
                return self._launch_game()

        return None

    # ------------------------------------------------------------------
    # Sub-screen renderers
    # ------------------------------------------------------------------

    def _render_mode_select(self, screen, W, H, cx):
        sub = _FONT_SM.render(
            "Host a game or join an existing room using a code.",
            True, _MUTED)
        screen.blit(sub, sub.get_rect(center=(cx, 105)))

        bw, bh = 280, 70
        gap = 30
        y_center = H // 2 - 10
        mx, my = pygame.mouse.get_pos()

        # HOST button
        hr = pygame.Rect(0, 0, bw, bh)
        hr.center = (cx - bw // 2 - gap // 2, y_center)
        self._draw_big_btn(screen, hr, "🏠  HOST", _GREEN,
                           hover=hr.collidepoint(mx, my))
        self._btn_host = hr

        # JOIN button
        jr = pygame.Rect(0, 0, bw, bh)
        jr.center = (cx + bw // 2 + gap // 2, y_center)
        self._draw_big_btn(screen, jr, "🔗  JOIN", _BLUE,
                           hover=jr.collidepoint(mx, my))
        self._btn_join = jr

        hint = _FONT_SM.render("Host: create a room and share the code with your friend.",
                               True, _MUTED)
        screen.blit(hint, hint.get_rect(center=(cx, y_center + bh // 2 + 30)))
        hint2 = _FONT_SM.render("Join: enter the code your friend shared with you.",
                                True, _MUTED)
        screen.blit(hint2, hint2.get_rect(center=(cx, y_center + bh // 2 + 54)))

        pass

    def _render_host_waiting(self, screen, W, H, cx):
        """
        Shows the room code as soon as HOST is clicked (code is generated
        client-side, no need to wait for relay).  Shows relay status beneath.
        """
        # Show room code prominently — always, even while still connecting
        y = 130
        lbl = _FONT_SM.render("Share this code with your opponent:", True, _MUTED)
        screen.blit(lbl, lbl.get_rect(center=(cx, y)))

        # Code panel
        code_surf = _FONT_MONO.render(self._room_code, True, _GOLD)
        cr = code_surf.get_rect(center=(cx, y + 55))
        panel = cr.inflate(40, 20)
        pygame.draw.rect(screen, _PANEL, panel, border_radius=10)
        pygame.draw.rect(screen, _GOLD, panel, width=2, border_radius=10)
        screen.blit(code_surf, cr)

        # Sub-status depending on relay connection state
        if self._sub == _S_HOST_CONNECTING:
            # Still connecting to relay — show a spinner + note below the code
            net_status = (self._net_client.status
                          if self._net_client else "connecting")
            status_txt = f"Connecting to relay server… ({net_status})"
            status_col = _AMBER
        else:
            # Connected and room confirmed
            status_txt = "Waiting for opponent to join…"
            status_col = _AMBER

        status = _FONT_MED.render(status_txt, True, status_col)
        screen.blit(status, status.get_rect(center=(cx, y + 115)))
        self._render_spinner(screen, cx, y + 155, "")

        hint = _FONT_SM.render(
            "Your opponent clicks 'Play over Web' → 'Join' and enters the code above.",
            True, _MUTED)
        screen.blit(hint, hint.get_rect(center=(cx, y + 200)))

    def _render_host_color_select(self, screen, W, H, cx):
        y = 130
        ok = _FONT_MED.render("✓ Opponent connected!", True, _GREEN)
        screen.blit(ok, ok.get_rect(center=(cx, y)))

        lbl = _FONT_SM.render("Choose your colour:", True, _TEXT)
        screen.blit(lbl, lbl.get_rect(center=(cx, y + 45)))

        bw, bh = 200, 60
        gap = 24
        mx, my = pygame.mouse.get_pos()

        wr = pygame.Rect(0, 0, bw, bh)
        wr.center = (cx - bw // 2 - gap // 2, y + 100)
        self._draw_color_btn(screen, wr, "WHITE", is_white=True,
                             selected=(self._host_color == "white"),
                             hover=wr.collidepoint(mx, my))
        self._btn_white = wr

        br = pygame.Rect(0, 0, bw, bh)
        br.center = (cx + bw // 2 + gap // 2, y + 100)
        self._draw_color_btn(screen, br, "BLACK", is_white=False,
                             selected=(self._host_color == "black"),
                             hover=br.collidepoint(mx, my))
        self._btn_black = br

        # Joiner colour info
        joiner_col = "Black" if self._host_color == "white" else "White"
        info = _FONT_SM.render(
            f"Your opponent will play as {joiner_col}.", True, _MUTED)
        screen.blit(info, info.get_rect(center=(cx, y + 165)))

        # Ready button
        rr = pygame.Rect(0, 0, 220, 52)
        rr.center = (cx, y + 220)
        self._draw_btn(screen, rr, "✓  READY", hover=rr.collidepoint(mx, my),
                       color=_GREEN)
        self._btn_ready = rr

        hint = _FONT_SM.render("Click Ready when both players are set.", True, _MUTED)
        screen.blit(hint, hint.get_rect(center=(cx, y + 280)))

    def _render_ready_wait(self, screen, W, H, cx, is_host: bool):
        y = H // 2 - 60
        if is_host:
            msg = "You are Ready! Waiting for opponent to confirm…"
        else:
            msg = "You are Ready! Waiting for host to confirm…"
        s = _FONT_MED.render(msg, True, _GREEN)
        screen.blit(s, s.get_rect(center=(cx, y)))
        self._render_spinner(screen, cx, y + 55, "")

    def _render_join_input(self, screen, W, H, cx):
        y = 130
        lbl = _FONT_SM.render("Enter the room code shared by your host:", True, _MUTED)
        screen.blit(lbl, lbl.get_rect(center=(cx, y)))

        # Text input box
        fw, fh = 260, 60
        fr = pygame.Rect(0, 0, fw, fh)
        fr.center = (cx, y + 60)
        pygame.draw.rect(screen, _PANEL2, fr, border_radius=8)
        pygame.draw.rect(screen, _GOLD if len(self._input_text) > 0 else _BORDER,
                         fr, width=2, border_radius=8)

        display = self._input_text.upper()
        if self._cursor_vis:
            display += "█"
        t = _FONT_MONO.render(display, True, _GOLD if display else _MUTED)
        screen.blit(t, t.get_rect(center=fr.center))

        # Connect button
        mx, my = pygame.mouse.get_pos()
        cr = pygame.Rect(0, 0, 200, 50)
        cr.center = (cx, y + 130)
        enabled = len(self._input_text) >= 6
        self._draw_btn(screen, cr, "CONNECT →",
                       hover=cr.collidepoint(mx, my) and enabled,
                       color=_BLUE if enabled else _MUTED)
        self._btn_connect = cr if enabled else None

        # Last-used code hint
        saved = self.config.last_room_code
        if saved and saved.upper() != self._input_text.upper():
            hint_txt = f"Last used: {saved.upper()}  —  click to use"
            hint_s   = _FONT_SM.render(hint_txt, True, _AMBER)
            hr = hint_s.get_rect(center=(cx, y + 185))
            screen.blit(hint_s, hr)
            # Store clickable region for "use last code" shortcut
            self._btn_use_last = hint_s.get_rect(center=(cx, y + 185))
        else:
            self._btn_use_last = None

        hint = _FONT_SM.render("Type the 6-character code and click Connect.", True, _MUTED)
        screen.blit(hint, hint.get_rect(center=(cx, y + 210)))

        if self._error_msg:
            err = _FONT_SM.render(self._error_msg, True, _RED)
            screen.blit(err, err.get_rect(center=(cx, y + 235)))

    def _render_join_waiting_color(self, screen, W, H, cx):
        y = H // 2 - 80
        ok = _FONT_MED.render("✓ Connected to room!", True, _GREEN)
        screen.blit(ok, ok.get_rect(center=(cx, y)))

        wait = _FONT_SM.render("Waiting for host to choose the colours…", True, _MUTED)
        screen.blit(wait, wait.get_rect(center=(cx, y + 40)))
        self._render_spinner(screen, cx, y + 90, "")

        hint = _FONT_SM.render(
            "The host will pick White or Black — you'll get the other.",
            True, _MUTED)
        screen.blit(hint, hint.get_rect(center=(cx, y + 140)))

        # If colour already assigned, show it and ready button
        if self._local_color:
            col_txt = self._local_color.upper()
            col_col = _WHITE_COL if self._local_color == "white" else _BLACK_COL
            cs = _FONT_MED.render(f"You will play as  {col_txt}", True, col_col)
            screen.blit(cs, cs.get_rect(center=(cx, y + 185)))
            self._sub = _S_JOIN_WAITING_COL  # keep until both ready

    def _render_ready_wait_joiner_with_color(self, screen, W, H, cx):
        """Called from join_waiting_color once colour is known and ready clicked."""
        y = H // 2 - 40
        col_txt = self._local_color.upper()
        cs = _FONT_MED.render(f"Playing as {col_txt} — READY!", True, _GREEN)
        screen.blit(cs, cs.get_rect(center=(cx, y)))
        self._render_spinner(screen, cx, y + 50, "Waiting for host to confirm…")

    def _render_countdown(self, screen, W, H, cx):
        remaining = self._COUNTDOWN_SEC - self._countdown
        number = max(1, int(math.ceil(remaining)))
        alpha = int(255 * (remaining % 1.0))
        pulse = 1.0 + 0.15 * math.sin(self._time * 8)

        n_surf = _FONT_MONO.render(str(number), True, _GOLD)
        scaled = pygame.transform.rotozoom(n_surf, 0, pulse)
        screen.blit(scaled, scaled.get_rect(center=(cx, H // 2 - 20)))

        go = _FONT_MED.render("Game starting…", True, _TEXT)
        screen.blit(go, go.get_rect(center=(cx, H // 2 + 60)))

        col_txt = self._local_color.upper()
        your = _FONT_SM.render(f"You are playing as  {col_txt}", True,
                               _WHITE_COL if self._local_color == "white" else _BLACK_COL)
        screen.blit(your, your.get_rect(center=(cx, H // 2 + 95)))

    def _render_error(self, screen, W, H, cx):
        y = H // 2 - 40
        e = _FONT_MED.render("Connection Error", True, _RED)
        screen.blit(e, e.get_rect(center=(cx, y)))
        m = _FONT_SM.render(self._error_msg, True, _TEXT)
        screen.blit(m, m.get_rect(center=(cx, y + 40)))
        hint = _FONT_SM.render("Press ESC or Back to return to menu.", True, _MUTED)
        screen.blit(hint, hint.get_rect(center=(cx, y + 75)))

    def _render_spinner(self, screen, cx, cy, label: str):
        """Draw a spinning arc to indicate waiting."""
        r = 18
        rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
        start = math.radians(self._spinner_angle)
        pygame.draw.arc(screen, _BLUE, rect, start, start + math.pi * 1.4, 4)
        if label:
            ls = _FONT_SM.render(label, True, _MUTED)
            screen.blit(ls, ls.get_rect(center=(cx, cy + r + 14)))

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    def _draw_btn(self, screen, rect, label, hover=False, color=_BLUE):
        bg = tuple(min(255, c + 30) for c in color) if hover else color
        pygame.draw.rect(screen, bg, rect, border_radius=8)
        pygame.draw.rect(screen, _BORDER, rect, width=1, border_radius=8)
        s = _FONT_MED.render(label, True, (255, 255, 255))
        screen.blit(s, s.get_rect(center=rect.center))

    def _draw_big_btn(self, screen, rect, label, accent, hover=False):
        bg = _PANEL2 if hover else _PANEL
        border = accent
        pygame.draw.rect(screen, bg, rect, border_radius=12)
        pygame.draw.rect(screen, border, rect, width=2 if not hover else 3, border_radius=12)
        s = _FONT_MED.render(label, True, accent)
        screen.blit(s, s.get_rect(center=rect.center))

    def _draw_color_btn(self, screen, rect, label, is_white, selected, hover):
        bg   = (230, 230, 245) if is_white else (30, 35, 50)
        fg   = (20, 20, 20)    if is_white else (220, 220, 230)
        bdr  = _GOLD if selected else (_BORDER if not hover else _BLUE)
        bdrw = 3 if selected else (2 if hover else 1)
        pygame.draw.rect(screen, bg, rect, border_radius=10)
        pygame.draw.rect(screen, bdr, rect, width=bdrw, border_radius=10)
        s = _FONT_MED.render(label, True, fg)
        screen.blit(s, s.get_rect(center=rect.center))

    # ------------------------------------------------------------------
    # Click handling
    # ------------------------------------------------------------------

    def _handle_click(self, pos) -> AppState | None:
        # Back / Menu button — always checked first
        if self._btn_back and self._btn_back.collidepoint(pos):
            if self._sub == _S_MODE_SELECT:
                # The ← Menu button on the first screen goes straight to MENU
                self._reset()
                return AppState.MENU
            else:
                self._go_back()   # returns to mode_select
            return None

        sub = self._sub

        if sub == _S_MODE_SELECT:
            if self._btn_host and self._btn_host.collidepoint(pos):
                self._start_host()
            elif self._btn_join and self._btn_join.collidepoint(pos):
                self._sub = _S_JOIN_INPUT
                self._error_msg = ""
                self._input_text = ""

        elif sub == _S_HOST_COLOR_SELECT:
            if self._btn_white and self._btn_white.collidepoint(pos):
                self._host_color = "white"
                self._local_color = "white"
            elif self._btn_black and self._btn_black.collidepoint(pos):
                self._host_color = "black"
                self._local_color = "black"
            elif self._btn_ready and self._btn_ready.collidepoint(pos):
                self._host_click_ready()

        elif sub == _S_JOIN_WAITING_COL:
            if self._btn_ready and self._btn_ready.collidepoint(pos):
                self._joiner_click_ready()

        elif sub == _S_JOIN_INPUT:
            if self._btn_connect and self._btn_connect.collidepoint(pos):
                self._start_join()
            # Clicking the "Last used" hint auto-fills the code
            elif hasattr(self, '_btn_use_last') and self._btn_use_last and self._btn_use_last.collidepoint(pos):
                self._input_text = self.config.last_room_code[:6].upper()
                self._error_msg  = ""

        return None

    def _handle_text_input(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_BACKSPACE:
            self._input_text = self._input_text[:-1]
        elif event.key == pygame.K_RETURN:
            if len(self._input_text) >= 6:
                self._start_join()
        elif event.unicode and len(self._input_text) < 6:
            ch = event.unicode.upper()
            if ch in string.ascii_uppercase + string.digits:
                self._input_text += ch
        self._error_msg = ""

    def _go_back(self) -> None:
        if self._net_client:
            self._net_client.disconnect()
            self._net_client = None
        self._reset()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _start_host(self) -> None:
        from network.client import NetworkClient
        # Generate the room code client-side immediately so it can be displayed
        # right away — no need to wait for relay confirmation.
        self._room_code = _gen_room_code()
        self._token     = str(uuid.uuid4())
        self._role      = "host"
        # Jump straight to HOST_WAITING — the code is shown immediately;
        # relay status is shown as a sub-label until confirmation arrives.
        self._sub       = _S_HOST_CONNECTING

        self._net_client = NetworkClient()
        self._net_client.connect(
            url       = self.config.relay_server_url,
            room_code = self._room_code,
            role      = "host",
            token     = self._token,
        )
        # Persist the room code so the player can rejoin quickly
        self.config.last_room_code = self._room_code
        self.config.save()
        log.info("Hosting room %s", self._room_code)

    def _start_join(self) -> None:
        from network.client import NetworkClient
        code = self._input_text.upper().strip()
        if len(code) < 6:
            self._error_msg = "Please enter a 6-character room code."
            return

        self._room_code = code
        self._token     = str(uuid.uuid4())
        self._role      = "joiner"
        self._sub       = _S_JOIN_CONNECTING

        self._net_client = NetworkClient()
        self._net_client.connect(
            url       = self.config.relay_server_url,
            room_code = self._room_code,
            role      = "joiner",
            token     = self._token,
        )
        # Persist the room code so the player can rejoin quickly
        self.config.last_room_code = self._room_code
        self.config.save()
        log.info("Joining room %s", self._room_code)

    def _host_click_ready(self) -> None:
        from network import serialiser
        self._host_ready = True

        # Send colour choice + session config to relay (relay caches session config)
        self._net_client.send(
            serialiser.msg_color_choice(
                self._room_code,
                self._host_color,
                self.config,
            )
        )

        # Send ready signal — relay will broadcast start_game when both ready
        self._net_client.send(
            serialiser.msg_player_ready(
                self._room_code,
                "host",
                self._host_color,
            )
        )
        self._sub = _S_HOST_READY_WAIT
        log.info("Host ready — waiting for joiner")

    def _joiner_click_ready(self) -> None:
        from network import serialiser
        self._joiner_ready = True
        self._net_client.send(
            serialiser.msg_player_ready(
                self._room_code,
                "joiner",
                "",  # joiner doesn't set host_color; relay already has it
            )
        )
        self._sub = _S_JOIN_READY_WAIT
        log.info("Joiner ready — waiting for host")

    # ------------------------------------------------------------------
    # Network message handling (lobby phase)
    # ------------------------------------------------------------------

    def _handle_net_msg(self, msg: dict) -> AppState | None:
        mtype = msg.get("type")
        log.debug("Lobby net msg: %s", mtype)

        if mtype == "room_created":
            # Relay confirmed our room — move to waiting screen
            self._room_code = msg.get("room", self._room_code)
            self._token     = msg.get("token", self._token)
            self._sub       = _S_HOST_WAITING

        elif mtype == "room_joined":
            self._room_code = msg.get("room", self._room_code)
            self._token     = msg.get("token", self._token)
            self._sub       = _S_JOIN_WAITING_COL

        elif mtype == "opponent_joined":
            # Host gets notified that a joiner connected
            if self._role == "host":
                self._sub = _S_HOST_COLOR_SELECT

        elif mtype == "color_choice":
            # Joiner receives host's colour choice
            if self._role == "joiner":
                host_color = msg.get("host_color", "white")
                self._local_color = "black" if host_color == "white" else "white"
                self._session_cfg  = msg.get("session_config", {})
                # Stay on join_waiting_color but the render will now show colour + ready btn

        elif mtype == "player_ready":
            # Track peer's ready state
            role = msg.get("role", "")
            if role == "host" and self._role == "joiner":
                self._host_ready = True
            elif role == "joiner" and self._role == "host":
                self._joiner_ready = True

        elif mtype == "start_game":
            # Relay says both players are ready — begin countdown
            white_role = msg.get("white_role", "host")
            if self._role == "host":
                self._local_color = "white" if white_role == "host" else "black"
            else:
                self._local_color = "white" if white_role == "joiner" else "black"
            self._session_cfg = msg.get("session_config", self._session_cfg)
            self._sub         = _S_COUNTDOWN
            self._countdown   = 0.0
            log.info("start_game received — countdown starting. local_color=%s",
                     self._local_color)

        elif mtype == "error":
            self._error_msg = msg.get("msg", "Unknown error")
            self._sub = _S_ERROR if self._sub != _S_JOIN_INPUT else self._sub
            if self._sub == _S_JOIN_INPUT:
                self._error_msg = msg.get("msg", "Could not connect")

        return None

    # ------------------------------------------------------------------
    # Game launch
    # ------------------------------------------------------------------

    def _launch_game(self) -> AppState:
        """
        Store session info on app and signal transition to ONLINE_GAMEPLAY.
        The app will build OnlineGameplayScene from this dict.
        """
        import copy
        # Build a hybrid config: take local config, override game settings from host
        online_cfg = copy.copy(self.config)
        if self._session_cfg:
            online_cfg.layout_file  = self._session_cfg.get("layout_file",
                                                             self.config.layout_file)
            online_cfg.time_control = self._session_cfg.get("time_control",
                                                             self.config.time_control)
            online_cfg.neutral_ai   = self._session_cfg.get("neutral_ai",
                                                             self.config.neutral_ai)
        # IMPORTANT: theme, sfx_volume, music_volume are NOT overridden —
        # each player keeps their own visual/audio preferences.
        online_cfg.single_player = False  # never use AI opponent in online mode

        self.app.online_session = {
            "network_client": self._net_client,
            "local_color":    self._local_color,
            "is_host":        self._role == "host",
            "room_code":      self._room_code,
            "token":          self._token,
            "config":         online_cfg,
        }
        log.info("Launching online game: local_color=%s is_host=%s room=%s",
                 self._local_color, self._role == "host", self._room_code)
        return AppState.ONLINE_GAMEPLAY

    # ------------------------------------------------------------------
    # Join waiting color — extra ready button render pass
    # ------------------------------------------------------------------

    def render(self, screen: pygame.Surface) -> None:  # noqa: F811
        _fonts()
        W, H = screen.get_size()

        # Background
        if self._bg:
            if self._bg_size != (W, H):
                self._bg_scaled = pygame.transform.smoothscale(self._bg, (W, H))
                self._bg_size   = (W, H)
            screen.blit(self._bg_scaled, (0, 0))
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 170))
            screen.blit(ov, (0, 0))
        else:
            screen.fill(_BG_DARK)

        cx = W // 2

        # Back button — shown on all screens except countdown
        self._btn_back = None
        self._btn_ready = None
        if self._sub != _S_COUNTDOWN:
            br = pygame.Rect(20, 20, 100, 36)
            label = "← Menu" if self._sub == _S_MODE_SELECT else "← Back"
            self._draw_btn(screen, br, label,
                           hover=br.collidepoint(pygame.mouse.get_pos()),
                           color=_MUTED)
            self._btn_back = br

        # Title
        title_surf = _FONT_BIG.render("PLAY OVER WEB", True, _GOLD)
        screen.blit(title_surf, title_surf.get_rect(center=(cx, 60)))

        # Sub-screen
        sub = self._sub
        if sub == _S_MODE_SELECT:
            self._render_mode_select(screen, W, H, cx)
        elif sub == _S_HOST_CONNECTING:
            # Room code already known — show it now with relay status below
            self._render_host_waiting(screen, W, H, cx)
        elif sub == _S_HOST_WAITING:
            self._render_host_waiting(screen, W, H, cx)
        elif sub == _S_HOST_COLOR_SELECT:
            self._render_host_color_select(screen, W, H, cx)
        elif sub == _S_HOST_READY_WAIT:
            self._render_ready_wait(screen, W, H, cx, is_host=True)
        elif sub == _S_JOIN_INPUT:
            self._render_join_input(screen, W, H, cx)
        elif sub == _S_JOIN_CONNECTING:
            self._render_spinner(screen, cx, H // 2, "Connecting to relay server…")
        elif sub == _S_JOIN_WAITING_COL:
            self._render_join_waiting_with_ready(screen, W, H, cx)
        elif sub == _S_JOIN_READY_WAIT:
            self._render_ready_wait(screen, W, H, cx, is_host=False)
        elif sub == _S_COUNTDOWN:
            self._render_countdown(screen, W, H, cx)
        elif sub == _S_ERROR:
            self._render_error(screen, W, H, cx)

        # Relay URL
        url_surf = _FONT_SM.render(
            f"Relay: {self.config.relay_server_url}", True, _MUTED)
        screen.blit(url_surf, url_surf.get_rect(center=(cx, H - 20)))

    def _render_join_waiting_with_ready(self, screen, W, H, cx):
        """Join waiting screen — shows colour once assigned, then a Ready button."""
        y = H // 2 - 100
        ok = _FONT_MED.render("✓ Connected to room!", True, _GREEN)
        screen.blit(ok, ok.get_rect(center=(cx, y)))

        if not self._local_color:
            # Colour not yet assigned
            wait = _FONT_SM.render(
                "Waiting for host to choose the colours…", True, _MUTED)
            screen.blit(wait, wait.get_rect(center=(cx, y + 42)))
            self._render_spinner(screen, cx, y + 90, "")
            hint = _FONT_SM.render(
                "The host will pick White or Black — you'll get the other.",
                True, _MUTED)
            screen.blit(hint, hint.get_rect(center=(cx, y + 140)))
        else:
            # Colour assigned
            col_txt = self._local_color.upper()
            col_col = _WHITE_COL if self._local_color == "white" else _BLACK_COL
            cs = _FONT_MED.render(f"You will play as  {col_txt}", True, col_col)
            screen.blit(cs, cs.get_rect(center=(cx, y + 42)))

            hint = _FONT_SM.render(
                "Click Ready when you're set to start!", True, _MUTED)
            screen.blit(hint, hint.get_rect(center=(cx, y + 82)))

            mx, my = pygame.mouse.get_pos()
            rr = pygame.Rect(0, 0, 220, 52)
            rr.center = (cx, y + 135)
            if not self._joiner_ready:
                self._draw_btn(screen, rr, "✓  READY", hover=rr.collidepoint(mx, my),
                               color=_GREEN)
                self._btn_ready = rr
            else:
                self._draw_btn(screen, rr, "✓  READY — Waiting for host",
                               hover=False, color=_MUTED)
                self._btn_ready = None
