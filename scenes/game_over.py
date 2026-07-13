"""
scenes/game_over.py
===================
GameOverScene — translucent overlay shown when the game ends.

Extracted from KingsTrialApp._draw_game_over_overlay() in the old main.py.

Options:
  S → re-save record
  R → restart (→ CONFIRM_RESTART)
  Q / Escape → MAIN MENU
"""

from __future__ import annotations
import os
import logging
import pygame
from scenes.base_scene import Scene, AppState
import constants as C

log = logging.getLogger("KingsTrial.game_over")


class GameOverScene(Scene):
    """End-game overlay with result, scores, save status, and options."""

    def __init__(self, gameplay_scene, screen: pygame.Surface) -> None:
        self.gameplay = gameplay_scene
        self.screen   = screen

    def on_enter(self, prev_state: AppState | None = None) -> None:
        log.debug("GameOverScene entered")

    # ── Scene interface ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> AppState | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_s:
                self._save()
            elif event.key == pygame.K_r:
                self.gameplay.reset()
                return AppState.GAMEPLAY
            elif event.key in (pygame.K_q, pygame.K_ESCAPE):
                return AppState.MENU
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if getattr(self, '_restart_btn', None) and self._restart_btn.collidepoint(event.pos):
                self.gameplay.reset()
                return AppState.GAMEPLAY
            if getattr(self, '_menu_btn', None) and self._menu_btn.collidepoint(event.pos):
                return AppState.MENU
        return None

    def update(self, dt: float) -> AppState | None:
        return None

    def render(self, screen: pygame.Surface) -> None:
        # Draw frozen gameplay underneath
        self.gameplay.render(screen)

        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        screen.blit(overlay, (0, 0))

        cx, cy    = screen.get_rect().center
        font_big  = pygame.font.SysFont("dejavusansmono", 38, bold=True)
        font_med  = pygame.font.SysFont("dejavusansmono", 20)
        font_sm   = pygame.font.SysFont("dejavusansmono", 14)
        gs        = self.gameplay.gs

        # Result banner
        lbl = font_big.render(gs.status_msg, True, (255, 220, 80))
        screen.blit(lbl, lbl.get_rect(center=(cx, cy - 70)))

        # Scores
        sc = f"White: {gs.points['white']} pts   |   Black: {gs.points['black']} pts"
        screen.blit(font_med.render(sc, True, (220, 220, 220)),
                    font_med.size(sc) and pygame.Rect(0, 0, *font_med.size(sc)).move(
                        cx - font_med.size(sc)[0] // 2, cy - 20))

        # Save status
        saved_path = self.gameplay.saved_path
        save_msg   = f"Saved: {os.path.basename(saved_path)}" if saved_path else "Press S to save game record"
        screen.blit(font_sm.render(save_msg, True, (160, 200, 160)),
                    font_sm.size(save_msg) and pygame.Rect(0, 0, *font_sm.size(save_msg)).move(
                        cx - font_sm.size(save_msg)[0] // 2, cy + 25))

        # Buttons
        btn_font = pygame.font.SysFont("dejavusansmono", 18, bold=True)
        
        self._restart_btn = pygame.Rect(0, 0, 170, 44)
        self._restart_btn.center = (cx - 100, cy + 70)
        
        self._menu_btn = pygame.Rect(0, 0, 170, 44)
        self._menu_btn.center = (cx + 100, cy + 70)

        mx, my = pygame.mouse.get_pos()
        for rect, label in [
            (self._restart_btn, "RESTART (R)"),
            (self._menu_btn,    "MAIN MENU (Q)"),
        ]:
            hovered = rect.collidepoint(mx, my)
            btn_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            bg_col   = C.GRAYSCALE_UI["menu_btn_hover"] if hovered else C.GRAYSCALE_UI["menu_btn"]
            bdr_col  = (200, 210, 220, 255) if hovered else C.GRAYSCALE_UI["border"]

            pygame.draw.rect(btn_surf, bg_col, btn_surf.get_rect(), border_radius=6)
            pygame.draw.rect(btn_surf, bdr_col, btn_surf.get_rect(), width=2, border_radius=6)
            screen.blit(btn_surf, rect.topleft)
            
            tc = (255, 255, 255) if hovered else C.GRAYSCALE_UI["menu_btn_text"]
            lbl = btn_font.render(label, True, tc)
            screen.blit(lbl, lbl.get_rect(center=rect.center))

    # ── Internal ──────────────────────────────────────────────────────────

    def _save(self) -> None:
        from record_saver import save_game_record
        gs   = self.gameplay.gs
        path = save_game_record(gs, gs.status_msg, self.gameplay.config)
        self.gameplay.saved_path = path
        log.info("Re-saved: %s", path)
