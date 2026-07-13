"""
scenes/pause.py
===============
PauseScene — overlay drawn on top of a frozen gameplay frame.

Options:
  R / Resume button   → return to GAMEPLAY
  T / Restart button  → go to CONFIRM_RESTART
  S                   → save game record
  Q / Escape          → QUIT
"""

from __future__ import annotations
import logging
import pygame
from scenes.base_scene import Scene, AppState
import constants as C

log = logging.getLogger("KingsTrial.pause")


class PauseScene(Scene):
    """Translucent pause overlay with Resume / Restart / Save / Quit."""

    # Button layout (relative to screen centre)
    _BUTTONS = [
        ("Resume",    AppState.GAMEPLAY,        (  0, -80)),
        ("Save",      "save",                   (  0,   0)),
        ("End Game",  AppState.CONFIRM_RESTART,  (  0,  80)),
    ]

    def __init__(self, gameplay_scene, screen: pygame.Surface) -> None:
        self.gameplay   = gameplay_scene  # reference for save + render background
        self.screen     = screen
        self._btn_rects: list[tuple[str, AppState, pygame.Rect]] = []

    def on_enter(self, prev_state: AppState | None = None) -> None:
        log.debug("PauseScene entered")

    # ── Scene interface ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> AppState | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_p:
                return AppState.GAMEPLAY       # P toggles pause
            elif event.key in (pygame.K_ESCAPE, pygame.K_q):
                return AppState.QUIT
            elif event.key == pygame.K_s:
                return AppState.SAVE_GAME      # S → filename prompt

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for label, state, rect in self._btn_rects:
                if rect.collidepoint(event.pos):
                    if label == "Save":
                        return AppState.SAVE_GAME
                    return state

        return None

    def update(self, dt: float) -> AppState | None:
        # Clocks are frozen while paused — no update needed
        return None

    def render(self, screen: pygame.Surface) -> None:
        # Draw the frozen gameplay frame underneath
        self.gameplay.render(screen)

        # Translucent dark overlay
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))

        cx, cy   = screen.get_rect().center
        font_ttl = pygame.font.SysFont("dejavusansmono", 32, bold=True)
        font_btn = pygame.font.SysFont("dejavusansmono", 20)

        # Title
        lbl = font_ttl.render("⏸  PAUSED", True, C.GRAYSCALE_UI["panel_text"])
        screen.blit(lbl, lbl.get_rect(center=(cx, cy - 120)))

        # Buttons
        self._btn_rects = []
        mx, my = pygame.mouse.get_pos()
        for label, state, (ox, oy) in self._BUTTONS:
            rect = pygame.Rect(0, 0, 200, 44)
            rect.center = (cx + ox, cy + oy)
            
            hovered = rect.collidepoint(mx, my)
            btn_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            bg_col   = C.GRAYSCALE_UI["menu_btn_hover"] if hovered else C.GRAYSCALE_UI["menu_btn"]
            bdr_col  = (200, 210, 220, 255) if hovered else C.GRAYSCALE_UI["border"]

            pygame.draw.rect(btn_surf, bg_col, btn_surf.get_rect(), border_radius=6)
            pygame.draw.rect(btn_surf, bdr_col, btn_surf.get_rect(), width=2, border_radius=6)
            screen.blit(btn_surf, rect.topleft)
            
            tc = (255, 255, 255) if hovered else C.GRAYSCALE_UI["menu_btn_text"]
            lbl = font_btn.render(label, True, tc)
            screen.blit(lbl, lbl.get_rect(center=rect.center))
            self._btn_rects.append((label, state, rect))

    # ── Internal ──────────────────────────────────────────────────────────
    # (save is now handled by SaveGameScene via AppState.SAVE_GAME)
