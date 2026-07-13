"""
scenes/menu.py
==============
MenuScene — the main menu shown when the game starts.

Buttons:
  New Game  → opens SettingsScene (which then transitions to GAMEPLAY)
  Load Game → AppState.LOAD_GAME  (Step 16)
  Quit      → AppState.QUIT

The scene renders its own visually styled splash with the game title,
animated board accent, and glowing buttons.

On first launch the last-saved GameConfig is displayed in the settings.
"""

from __future__ import annotations
import math
import logging
import pygame

from scenes.base_scene import Scene, AppState
from config import GameConfig
import constants as C

log = logging.getLogger("KingsTrial.menu")

# Accent colours complementing the cinematic background
_GOLD    = (255, 215,  60)  # matching the warm golden daylight


class MenuScene(Scene):
    """
    Main menu screen.

    Keeps a reference to `app` so it can push `config` changes through
    to the App before transitioning to GAMEPLAY.
    """

    def __init__(self, app, screen: pygame.Surface) -> None:
        self.app    = app
        self.screen = screen
        self.config = app.config         # live reference

        self._time        = 0.0          # for idle animation
        self._btn_rects: list[tuple[str, AppState | str, pygame.Rect]] = []
        
        import os
        import ui.theme
        assets_dir = getattr(ui.theme.manager, "assets_dir", None)
        if assets_dir:
            bg_path = os.path.join(assets_dir, "menu_bg.png")
        else:
            bg_path = os.path.join(os.path.dirname(__file__), "..", "assets", "menu_bg.png")
        try:
            self.bg_image = pygame.image.load(bg_path).convert()
        except Exception as e:
            log.warning(f"Could not load menu_bg.png: {e}")
            self.bg_image = None
        self._scaled_bg = None
        self._bg_size = (0, 0)

        # ── FAQ Carousel Initialization ─────────────────────────────────────
        self.show_faq = False
        self.faq_index = 0
        self.faq_images = []
        
        if assets_dir:
            faq_dir = os.path.join(assets_dir, "FAQ")
        else:
            faq_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "FAQ")
            
        if os.path.exists(faq_dir):
            image_names = ["MAIN MENU.PNG", "GAME PLAY.PNG", "SETTINGS.PNG"]
            for img_name in image_names:
                img_path = os.path.join(faq_dir, img_name)
                if os.path.exists(img_path):
                    try:
                        surf = pygame.image.load(img_path).convert_alpha()
                        self.faq_images.append((img_name.replace(".PNG", ""), surf))
                    except Exception as e:
                        log.warning(f"Could not load FAQ image {img_name}: {e}")
            
            # Fallback: load any image in assets/FAQ if the specific list was empty
            if not self.faq_images:
                try:
                    for f in sorted(os.listdir(faq_dir)):
                        if f.lower().endswith((".png", ".jpg", ".jpeg")):
                            surf = pygame.image.load(os.path.join(faq_dir, f)).convert_alpha()
                            self.faq_images.append((os.path.splitext(f)[0], surf))
                except Exception as e:
                    log.warning(f"Error reading FAQ directory: {e}")
        
        self._faq_container_rect = None
        self._faq_close_rect = None
        self._faq_prev_rect = None
        self._faq_next_rect = None

    def on_enter(self, prev_state: AppState | None = None) -> None:
        log.debug("MenuScene entered from %s", prev_state)
        pygame.display.set_caption("King's Trial  ♟  Main Menu")

    # ── Scene interface ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> AppState | None:
        if self.show_faq:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    self.show_faq = False
                elif event.key in (pygame.K_LEFT, pygame.K_BACKSPACE):
                    if self.faq_images:
                        self.faq_index = (self.faq_index - 1) % len(self.faq_images)
                elif event.key in (pygame.K_RIGHT, pygame.K_SPACE):
                    if self.faq_images:
                        self.faq_index = (self.faq_index + 1) % len(self.faq_images)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                if getattr(self, "_faq_close_rect", None) and self._faq_close_rect.collidepoint(mx, my):
                    self.show_faq = False
                elif getattr(self, "_faq_prev_rect", None) and self._faq_prev_rect.collidepoint(mx, my):
                    if self.faq_images:
                        self.faq_index = (self.faq_index - 1) % len(self.faq_images)
                elif getattr(self, "_faq_next_rect", None) and self._faq_next_rect.collidepoint(mx, my):
                    if self.faq_images:
                        self.faq_index = (self.faq_index + 1) % len(self.faq_images)
                elif getattr(self, "_faq_container_rect", None) and not self._faq_container_rect.collidepoint(mx, my):
                    # Close when clicking outside the modal
                    self.show_faq = False
            return None

        # Standard menu events
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_ESCAPE):
            return AppState.QUIT

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for label, action, rect in self._btn_rects:
                if rect.collidepoint(event.pos):
                    if action == "faq":
                        self.show_faq = True
                        self.faq_index = 0
                        return None
                    return self._dispatch(label, action)

        return None

    def update(self, dt: float) -> AppState | None:
        self._time += dt
        return None

    def _scale_to_fit(self, image: pygame.Surface, max_w: int, max_h: int) -> pygame.Surface:
        img_w, img_h = image.get_size()
        scale = min(max_w / img_w, max_h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        return pygame.transform.smoothscale(image, (new_w, new_h))

    def render(self, screen: pygame.Surface) -> None:
        W, H = screen.get_size()
        cx = W // 2
        
        if getattr(self, 'bg_image', None):
            if self._bg_size != (W, H):
                self._scaled_bg = pygame.transform.smoothscale(self.bg_image, (W, H))
                self._bg_size = (W, H)
            screen.blit(self._scaled_bg, (0, 0))
        else:
            screen.fill(C.GRAYSCALE_UI["bg"])

        # Get Green & Cream colors from theme manager if available, otherwise use defaults
        import ui.theme
        theme = ui.theme.manager.current_theme if ui.theme.manager else None
        
        if theme:
            green_color = tuple(theme["pieces"]["neutral"]["badge"][:3])
            cream_color = tuple(theme["pieces"]["white"]["badge"][:3])
        else:
            green_color = (81, 154, 102)
            cream_color = (220, 220, 200)

        # ── Buttons Layout ──────────────────────────────────────────────────
        left_buttons = [
            ("New Game",       AppState.GAMEPLAY),
            ("Load Game",      AppState.LOAD_GAME),
            ("Play over Web",  AppState.ONLINE_LOBBY),
        ]
        right_buttons = [
            ("FAQ",            "faq"),
            ("Settings",       "settings"),
            ("Quit",           AppState.QUIT),
        ]
        
        self._btn_rects = []
        btn_w, btn_h = 260, 52
        v_gap        = 20
        h_gap        = 80
        start_y      = H // 2 + 50
        
        cx_left = cx - (btn_w // 2 + h_gap // 2)
        cx_right = cx + (btn_w // 2 + h_gap // 2)

        font_btn = pygame.font.SysFont("dejavusansmono", 20, bold=True)
        mx, my   = pygame.mouse.get_pos()
        
        # If FAQ is showing, disable hover and clicks on standard menu buttons
        if self.show_faq:
            mx, my = -1000, -1000

        # Draw Left Column (Green Themed)
        for i, (label, action) in enumerate(left_buttons):
            rect = pygame.Rect(0, 0, btn_w, btn_h)
            rect.center = (cx_left, start_y + i * (btn_h + v_gap))

            hovered = rect.collidepoint(mx, my)
            btn_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            
            # Opacities maximized: 240 (default for crisp, sharp text), 255 (fully opaque on hover)
            bg_alpha = 255 if hovered else 240
            bg_col = (*green_color, bg_alpha)
            bdr_col = (255, 255, 230, 255) if hovered else (*cream_color, 255)

            pygame.draw.rect(btn_surf, bg_col, btn_surf.get_rect(), border_radius=8)
            pygame.draw.rect(btn_surf, bdr_col, btn_surf.get_rect(), width=2, border_radius=8)
            screen.blit(btn_surf, rect.topleft)

            tc = (255, 255, 255) if hovered else cream_color
            lbl = font_btn.render(label, True, tc)
            screen.blit(lbl, lbl.get_rect(center=rect.center))
            self._btn_rects.append((label, action, rect))

        # Draw Right Column (Cream Themed)
        for i, (label, action) in enumerate(right_buttons):
            rect = pygame.Rect(0, 0, btn_w, btn_h)
            rect.center = (cx_right, start_y + i * (btn_h + v_gap))

            hovered = rect.collidepoint(mx, my)
            btn_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            
            # Opacities maximized: 240 (default for crisp, sharp text), 255 (fully opaque on hover)
            bg_alpha = 255 if hovered else 240
            bg_col = (*cream_color, bg_alpha)
            bdr_col = (47, 107, 63, 255) if hovered else (*green_color, 255)

            pygame.draw.rect(btn_surf, bg_col, btn_surf.get_rect(), border_radius=8)
            pygame.draw.rect(btn_surf, bdr_col, btn_surf.get_rect(), width=2, border_radius=8)
            screen.blit(btn_surf, rect.topleft)

            tc = (47, 107, 63) if hovered else green_color
            lbl = font_btn.render(label, True, tc)
            screen.blit(lbl, lbl.get_rect(center=rect.center))
            self._btn_rects.append((label, action, rect))

        # ── Version / hint ────────────────────────────────────────────────
        font_sub = pygame.font.SysFont("dejavusansmono", 18)
        hint = font_sub.render("v0.15  |  Q to quit", True, (60, 70, 100))
        screen.blit(hint, hint.get_rect(center=(cx, H - 28)))

        # ── FAQ Carousel Modal Overlay ──────────────────────────────────────
        if self.show_faq:
            real_mx, real_my = pygame.mouse.get_pos()
            
            # 1. Dim background
            dim_surf = pygame.Surface((W, H), pygame.SRCALPHA)
            dim_surf.fill((0, 0, 0, 190))
            screen.blit(dim_surf, (0, 0))
            
            # 2. Main Container Centred
            container_w, container_h = 1060, 630
            container_rect = pygame.Rect(cx - container_w // 2, H // 2 - container_h // 2, container_w, container_h)
            self._faq_container_rect = container_rect
            
            container_surf = pygame.Surface((container_w, container_h), pygame.SRCALPHA)
            container_surf.fill((24, 26, 30, 245))
            pygame.draw.rect(container_surf, green_color, container_surf.get_rect(), width=3, border_radius=12)
            screen.blit(container_surf, container_rect.topleft)
            
            # 3. Render Active FAQ Image First (Using absolute maximum container area: 1030 × 600)
            if self.faq_images:
                slide_title, img = self.faq_images[self.faq_index]
                max_w, max_h = 1030, 600
                scaled_img = self._scale_to_fit(img, max_w, max_h)
                
                # Image centered inside the entire modal container
                img_rect = scaled_img.get_rect(center=(cx, container_rect.centery))
                screen.blit(scaled_img, img_rect.topleft)
            else:
                font_caption = pygame.font.SysFont("dejavusansmono", 18)
                err_lbl = font_caption.render("No FAQ images found in assets/FAQ", True, (200, 100, 100))
                screen.blit(err_lbl, err_lbl.get_rect(center=(cx, H // 2)))

            # 4. Close Button (Overlapping in the top-right corner; styled like Cream themed buttons)
            close_rect = pygame.Rect(container_rect.right - 52, container_rect.top + 20, 32, 32)
            self._faq_close_rect = close_rect
            
            close_hovered = close_rect.collidepoint(real_mx, real_my)
            close_surf = pygame.Surface((close_rect.w, close_rect.h), pygame.SRCALPHA)
            close_bg_alpha = 255 if close_hovered else 240
            close_bg = (*cream_color, close_bg_alpha)
            close_bdr = (47, 107, 63, 255) if close_hovered else (*green_color, 255)
            
            pygame.draw.rect(close_surf, close_bg, close_surf.get_rect(), border_radius=6)
            pygame.draw.rect(close_surf, close_bdr, close_surf.get_rect(), width=2, border_radius=6)
            screen.blit(close_surf, close_rect.topleft)
            
            font_close = pygame.font.SysFont("dejavusansmono", 18, bold=True)
            close_tc = (47, 107, 63) if close_hovered else green_color
            close_lbl = font_close.render("X", True, close_tc)
            screen.blit(close_lbl, close_lbl.get_rect(center=close_rect.center))
            
            # 5. Prev & Next Navigation Buttons (Overlapping on left/right edges; styled like Green themed buttons)
            prev_rect = pygame.Rect(container_rect.left + 20, container_rect.centery - 20, 40, 40)
            next_rect = pygame.Rect(container_rect.right - 60, container_rect.centery - 20, 40, 40)
            self._faq_prev_rect = prev_rect
            self._faq_next_rect = next_rect
            
            prev_hovered = prev_rect.collidepoint(real_mx, real_my)
            next_hovered = next_rect.collidepoint(real_mx, real_my)
            
            font_nav = pygame.font.SysFont("dejavusansmono", 22, bold=True)
            
            # Prev Button
            prev_surf = pygame.Surface((prev_rect.w, prev_rect.h), pygame.SRCALPHA)
            prev_bg_alpha = 255 if prev_hovered else 240
            prev_bg = (*green_color, prev_bg_alpha)
            prev_bdr = (255, 255, 230, 255) if prev_hovered else (*cream_color, 255)
            
            pygame.draw.rect(prev_surf, prev_bg, prev_surf.get_rect(), border_radius=8)
            pygame.draw.rect(prev_surf, prev_bdr, prev_surf.get_rect(), width=2, border_radius=8)
            screen.blit(prev_surf, prev_rect.topleft)
            
            prev_tc = (255, 255, 255) if prev_hovered else cream_color
            prev_lbl = font_nav.render("<", True, prev_tc)
            screen.blit(prev_lbl, prev_lbl.get_rect(center=prev_rect.center))
            
            # Next Button
            next_surf = pygame.Surface((next_rect.w, next_rect.h), pygame.SRCALPHA)
            next_bg_alpha = 255 if next_hovered else 240
            next_bg = (*green_color, next_bg_alpha)
            next_bdr = (255, 255, 230, 255) if next_hovered else (*cream_color, 255)
            
            pygame.draw.rect(next_surf, next_bg, next_surf.get_rect(), border_radius=8)
            pygame.draw.rect(next_surf, next_bdr, next_surf.get_rect(), width=2, border_radius=8)
            screen.blit(next_surf, next_rect.topleft)
            
            next_tc = (255, 255, 255) if next_hovered else cream_color
            next_lbl = font_nav.render(">", True, next_tc)
            screen.blit(next_lbl, next_lbl.get_rect(center=next_rect.center))

    # ── Internal ──────────────────────────────────────────────────────────

    def _dispatch(self, label: str, action) -> AppState | None:
        if label == "New Game":
            self.app._gameplay.reset()

        if action == "settings":
            # Push a settings scene if not already registered
            from scenes.settings import SettingsScene
            self.app._scenes[AppState.MENU] = self   # keep self in MENU
            settings_sc = SettingsScene(self.app, self.screen, back_state=AppState.MENU)
            self.app._scenes["_settings"] = settings_sc
            self.app._transition_to_scene(settings_sc, "_settings")
            return None

        if isinstance(action, AppState):
            return action

        return None
