"""
scenes/save_game.py
===================
SaveGameScene — text-input prompt for naming a save file.

Shown when the player clicks Save in the Pause menu (or Game Over screen).
Player types a name → saved as {name}_{YYYYMMDD_HHMMSS}.kgt

Press Enter  → save and return to back_state
Press Escape → cancel and return to back_state
"""

from __future__ import annotations
import os
import datetime
import logging
import pygame

from scenes.base_scene import Scene, AppState
from record_saver import save_game_record

log = logging.getLogger("KingsTrial.save_game")

_BG     = ( 18,  20,  30)
_PANEL  = ( 28,  32,  48)
_BORDER = ( 80,  90, 130)
_GOLD   = (255, 215,  60)
_FG     = (200, 210, 230)
_DIM    = ( 80,  90, 110)
_OK     = ( 70, 200, 120)
_ERR    = (200,  70,  70)

_MAX_NAME_LEN = 40
_ALLOWED = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789 _-.()"
)


class SaveGameScene(Scene):
    """
    Single-purpose text-input scene for naming a save file.

    Caller supplies:
        gameplay_scene  — GameplayScene (to access gs and saved_path)
        result_msg      — the status/result string to embed in the save
        back_state      — AppState to return to after save or cancel
    """

    def __init__(self, app, screen: pygame.Surface,
                 gameplay_scene,
                 back_state: AppState = AppState.PAUSED) -> None:
        self.app      = app
        self.screen   = screen
        self.gameplay = gameplay_scene
        self.back_state = back_state

        self._text:    str  = ""
        self._message: str  = "Enter a name for the save file:"
        self._msg_col        = _FG
        self._cursor_vis: bool = True
        self._cursor_t: float  = 0.0
        self._save_rect: pygame.Rect | None = None
        self._cancel_rect: pygame.Rect | None = None

    def on_enter(self, prev_state: AppState | None = None) -> None:
        pygame.display.set_caption("King's Trial  ♟  Save Game")
        self._text    = ""
        self._message = "Enter a name for the save file:"
        self._msg_col = _FG
        self._cursor_vis = True
        self._cursor_t   = 0.0
        # Start keyboard events flowing through pygame's text input
        pygame.key.set_repeat(400, 40)

    def on_exit(self) -> None:
        pygame.key.set_repeat(0)

    # ── Scene interface ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> AppState | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return self.back_state

            elif event.key == pygame.K_RETURN:
                return self._do_save()

            elif event.key == pygame.K_BACKSPACE:
                self._text = self._text[:-1]

            else:
                ch = event.unicode
                if ch and ch in _ALLOWED and len(self._text) < _MAX_NAME_LEN:
                    self._text += ch

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._save_rect and self._save_rect.collidepoint(event.pos):
                return self._do_save()
            if self._cancel_rect and self._cancel_rect.collidepoint(event.pos):
                return self.back_state

        return None

    def update(self, dt: float) -> AppState | None:
        self._cursor_t += dt
        if self._cursor_t >= 0.5:
            self._cursor_vis = not self._cursor_vis
            self._cursor_t   = 0.0
        return None

    def render(self, screen: pygame.Surface) -> None:
        # Background: frozen paused frame under a dark overlay
        self.gameplay.render(screen)
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        screen.blit(overlay, (0, 0))

        W, H = screen.get_size()
        cx, cy = W // 2, H // 2

        font_ttl = pygame.font.SysFont("dejavusansmono", 22, bold=True)
        font_sub = pygame.font.SysFont("dejavusansmono", 15)
        font_inp = pygame.font.SysFont("dejavusansmono", 18)
        font_btn = pygame.font.SysFont("dejavusansmono", 16, bold=True)

        # Panel box
        panel = pygame.Rect(cx - 340, cy - 120, 680, 240)
        pygame.draw.rect(screen, _PANEL, panel, border_radius=10)
        pygame.draw.rect(screen, _BORDER, panel, width=2, border_radius=10)

        # Title
        ttl = font_ttl.render("Save Game", True, _GOLD)
        screen.blit(ttl, ttl.get_rect(center=(cx, cy - 90)))

        # Prompt / message
        msg = font_sub.render(self._message, True, self._msg_col)
        screen.blit(msg, msg.get_rect(center=(cx, cy - 55)))

        # Text input box
        inp_rect = pygame.Rect(cx - 280, cy - 32, 560, 40)
        pygame.draw.rect(screen, (22, 26, 40), inp_rect, border_radius=5)
        pygame.draw.rect(screen, _GOLD, inp_rect, width=2, border_radius=5)

        display_text = self._text + ("|" if self._cursor_vis else " ")
        inp_lbl = font_inp.render(display_text, True, _FG)
        screen.blit(inp_lbl, (inp_rect.x + 8, inp_rect.centery - inp_lbl.get_height() // 2))

        # Filename preview
        if self._text.strip():
            ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            preview = f"→  {self._text.strip()}_{ts}.kgt"
        else:
            preview = "→  (Please enter a name)"
        pv_col = _DIM if not self._text.strip() else (120, 150, 200)
        pv = font_sub.render(preview, True, pv_col)
        screen.blit(pv, pv.get_rect(center=(cx, cy + 22)))

        # Buttons
        for label, color, is_save in [
            ("Save  ↵", (60, 130, 60), True),
            ("Cancel", (80, 50, 50), False),
        ]:
            bx = cx - 165 if is_save else cx + 15
            rect = pygame.Rect(bx, cy + 55, 150, 38)
            active = is_save and bool(self._text.strip())
            bg     = color if active else tuple(max(0, c - 30) for c in color)
            pygame.draw.rect(screen, bg, rect, border_radius=6)
            lbl = font_btn.render(label, True, _FG if active else _DIM)
            screen.blit(lbl, lbl.get_rect(center=rect.center))
            if is_save:
                self._save_rect = rect
            else:
                self._cancel_rect = rect

    # ── Internal ──────────────────────────────────────────────────────────

    def _do_save(self) -> AppState | None:
        name = self._text.strip()
        if not name:
            self._message = "Please enter a name first."
            self._msg_col = _ERR
            return None

        ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{ts}.kgt"
        # Save in the dedicated saves folder, not the current working directory.
        from record_saver import _SAVE_DIR
        path     = os.path.join(_SAVE_DIR, filename)

        result = self.gameplay.gs.status_msg or "Game in progress"
        try:
            save_game_record(self.gameplay.gs, result, path=path)
            self.gameplay.saved_path = path
            log.info("SaveGame: written to %s", path)
            self._message = f"Saved: {filename}"
            self._msg_col = _OK
        except Exception as exc:
            log.error("SaveGame: failed — %s", exc)
            self._message = f"Save failed: {exc}"
            self._msg_col = _ERR
            return None

        return self.back_state
