"""
scenes/confirm.py
=================
ConfirmScene — "Are you sure you want to end game?"

Behaviour (per user spec):
  YES → return to MAIN MENU
  NO  → return to PAUSED
"""

from __future__ import annotations
import logging
import pygame
from scenes.base_scene import Scene, AppState

log = logging.getLogger("KingsTrial.confirm")


class ConfirmRestartScene(Scene):
    """Modal confirm-restart dialog."""

    def __init__(self, gameplay_scene, screen: pygame.Surface) -> None:
        self.gameplay = gameplay_scene
        self.screen   = screen
        self._yes_rect: pygame.Rect | None = None
        self._no_rect:  pygame.Rect | None = None
        self._back_state = AppState.PAUSED

    def on_enter(self, prev_state: AppState | None = None) -> None:
        log.debug("ConfirmRestartScene entered")
        self._back_state = prev_state if prev_state else AppState.PAUSED

    # ── Scene interface ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> AppState | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_y:
                return self._do_restart()
            elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                return self._back_state

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._yes_rect and self._yes_rect.collidepoint(event.pos):
                return self._do_restart()
            if self._no_rect and self._no_rect.collidepoint(event.pos):
                return self._back_state

        return None

    def update(self, dt: float) -> AppState | None:
        return None

    def render(self, screen: pygame.Surface) -> None:
        # Background: frozen paused frame
        self.gameplay.render(screen)
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))

        cx, cy   = screen.get_rect().center
        font_ttl = pygame.font.SysFont("dejavusansmono", 24, bold=True)
        font_sub = pygame.font.SysFont("dejavusansmono", 16)
        font_btn = pygame.font.SysFont("dejavusansmono", 18, bold=True)

        # Message
        lines   = [
            "End Game?",
            "",
            "Return to the main menu?",
        ]
        for i, line in enumerate(lines):
            lbl = (font_ttl if i == 0 else font_sub).render(line, True, (230, 220, 200))
            screen.blit(lbl, lbl.get_rect(center=(cx, cy - 100 + i * 30)))

        # Buttons
        yes_rect = pygame.Rect(0, 0, 140, 44)
        no_rect  = pygame.Rect(0, 0, 140, 44)
        yes_rect.center = (cx - 80, cy + 70)
        no_rect.center  = (cx + 80, cy + 70)

        for rect, label in [
            (yes_rect, "YES (Y)"),
            (no_rect,  "NO  (N)"),
        ]:
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            btn_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            bg_alpha = 220 if hovered else 180
            bg_col   = (75, 80, 85, bg_alpha) if hovered else (40, 42, 45, bg_alpha)
            bdr_col  = (200, 210, 220, 255) if hovered else (100, 105, 110, 200)

            pygame.draw.rect(btn_surf, bg_col, btn_surf.get_rect(), border_radius=6)
            pygame.draw.rect(btn_surf, bdr_col, btn_surf.get_rect(), width=2, border_radius=6)
            screen.blit(btn_surf, rect.topleft)
            
            tc = (255, 255, 255) if hovered else (200, 210, 220)
            lbl = font_btn.render(label, True, tc)
            screen.blit(lbl, lbl.get_rect(center=rect.center))

        self._yes_rect = yes_rect
        self._no_rect  = no_rect

    # ── Internal ──────────────────────────────────────────────────────────

    def _do_restart(self) -> AppState:
        log.info("Ending game from pause menu and returning to main menu.")
        # No auto-save — player may save manually from pause/game-over screen
        # Reset gameplay
        self.gameplay.reset()
        return AppState.MENU
