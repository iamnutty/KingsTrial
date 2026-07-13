"""
scenes/settings.py
==================
SettingsScene — in-game settings panel accessible from the main menu.

Covers:
  • Mode: 2-Player vs Single Player (with player colour picker)
  • Neutral AI level
  • Opponent AI level  (visible only in single-player mode)
  • Theme
  • SFX / Music toggles

Changes are applied live to app.config and persisted to config.json
when the player clicks "Save & Back".
"""

import logging
import pygame
import os

from scenes.base_scene import Scene, AppState
from config import GameConfig, AI_LEVELS
import constants as C

log = logging.getLogger("KingsTrial.settings")


def _render_text(screen, font, text, color, center):
    lbl = font.render(text, True, color)
    screen.blit(lbl, lbl.get_rect(center=center))


class SettingsScene(Scene):
    """Interactive settings panel."""

    _AI_KEYS = list(AI_LEVELS.keys())   # ["random", "easy", "medium", "hard", "expert"]
    _COLOURS = ["white", "black", "random"]
    _TIME_KEYS = ["2+5", "5+10", "10+20"]

    def __init__(self, app, screen: pygame.Surface, back_state: AppState | str = AppState.MENU) -> None:
        self.app        = app
        self.screen     = screen
        self.back_state = back_state

        # Work on a copy so Cancel discards changes
        self._cfg       = GameConfig(**vars(app.config))
        self._clickables: list[tuple[str, object, pygame.Rect]] = []
        self._dropdown_rects: list[tuple[str, object, pygame.Rect]] = []
        self._active_dropdown: str | None = None

        # Relay URL text input state
        self._relay_editing  = False          # True when the URL field is focused
        self._relay_text     = self._cfg.relay_server_url
        self._relay_cursor   = len(self._relay_text)
        self._relay_blink    = 0.0
        self._relay_cur_vis  = True
        self._relay_error    = ""             # validation error message
        
        theme_dir = "assets/themes"
        if os.path.exists(theme_dir):
            self._available_themes = [f[:-5] for f in os.listdir(theme_dir) if f.endswith(".json")]
        else:
            self._available_themes = ["default"]
            
        map_dir = "assets/maps"
        if os.path.exists(map_dir):
            self._available_maps = [f for f in os.listdir(map_dir) if f.endswith(".csv")]
        else:
            self._available_maps = ["TEST_CSV.csv"]

    def on_enter(self, prev_state: AppState | None = None) -> None:
        log.debug("SettingsScene entered")
        pygame.display.set_caption("King's Trial  ♟  Settings")
        # Re-sync relay text in case we re-enter settings
        self._relay_text    = self._cfg.relay_server_url
        self._relay_cursor  = len(self._relay_text)
        self._relay_editing = False
        self._relay_error   = ""

    # ── Scene interface ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> AppState | None:
        if event.type == pygame.KEYDOWN:
            if self._relay_editing:
                # Relay URL text field is active — capture all key presses
                return self._handle_relay_key(event)

            if event.key == pygame.K_ESCAPE:
                if self._active_dropdown:
                    self._active_dropdown = None
                    return None
                return self._back()

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Clicking anywhere outside the relay box deactivates it
            if self._relay_editing:
                if not (hasattr(self, '_relay_rect') and self._relay_rect.collidepoint(event.pos)):
                    self._commit_relay_url()

            if self._active_dropdown:
                # If a dropdown is open, only check its options
                for name, value, rect in self._dropdown_rects:
                    if rect.collidepoint(event.pos):
                        self._active_dropdown = None
                        return self._handle_click(name, value)
                # Clicked outside dropdown -> close it
                self._active_dropdown = None
                return None
            else:
                for name, value, rect in self._clickables:
                    if rect.collidepoint(event.pos):
                        return self._handle_click(name, value)

        return None

    def update(self, dt: float) -> AppState | None:
        # Cursor blink for relay URL input
        if self._relay_editing:
            self._relay_blink += dt
            if self._relay_blink > 0.5:
                self._relay_blink  = 0.0
                self._relay_cur_vis = not self._relay_cur_vis
        return None

    def render(self, screen: pygame.Surface) -> None:
        screen.fill(C.GRAYSCALE_UI["bg"])
        W, H = screen.get_size()
        cx = W // 2
        self._clickables = []

        self._dropdown_rects = []
        dropdown_state_to_draw = None

        font_ttl = pygame.font.SysFont("dejavusansmono", 28, bold=True)
        font_hdr = pygame.font.SysFont("dejavusansmono", 14, bold=True)
        font_val = pygame.font.SysFont("dejavusansmono", 14)
        font_btn = pygame.font.SysFont("dejavusansmono", 16, bold=True)

        # Draw central settings card panel
        panel_rect = pygame.Rect(50, 40, W - 100, H - 80)
        pygame.draw.rect(screen, C.GRAYSCALE_UI["panel_bg"], panel_rect, border_radius=10)
        pygame.draw.rect(screen, C.GRAYSCALE_UI["border"], panel_rect, width=2, border_radius=10)

        _render_text(screen, font_ttl, "Settings", C.GRAYSCALE_UI["panel_text"], (cx, 70))

        # Group rows into Left and Right Columns
        left_rows: list[tuple[str, list, bool]] = [
            ("GAME MODE",      self._row_toggle("single_player",
                                                [(False, "2 Player"), (True, "vs AI")]), False),
        ]

        if self._cfg.single_player:
            left_rows.append(("PLAYER COLOUR", self._row_cycle("human_colour", self._COLOURS), False))
            left_rows.append(("OPPONENT AI",   self._row_cycle("opponent_ai",  self._AI_KEYS), False))

        left_rows += [
            ("NEUTRAL AI",    self._row_cycle("neutral_ai",  self._AI_KEYS), False),
            ("TIME CONTROL",  self._row_cycle_tc("time_control", self._TIME_KEYS), True),
            ("INITIAL MAP",   self._row_cycle("layout_file", self._available_maps), True),
        ]

        # Get server options list, ensuring current URL is included
        opts = getattr(self._cfg, "relay_server_options", [
            "wss://kings-trial-server.fly.dev",
            "ws://localhost:8765"
        ])
        cur_url = self._cfg.relay_server_url
        if cur_url not in opts:
            opts = [cur_url] + [o for o in opts if o != cur_url]

        right_rows: list[tuple[str, list, bool]] = [
            ("THEME",         self._row_cycle("theme",       self._available_themes), True),
            ("SOUND FX",      self._row_toggle("sfx_volume",
                                               [(0, "Off"), (1, "Low"), (2, "Med"), (3, "Max")]), False),
            ("MUSIC",         self._row_toggle("music_volume",
                                               [(0, "Off"), (1, "Low"), (2, "Med"), (3, "Max")]), False),
            ("RELAY SERVER",  self._row_cycle_relay("relay_server_url", opts), True),
        ]

        start_y = 120
        row_h  = 52
        
        # Coordinates for 2-column layout
        col1_lbl_x = 160
        col1_val_x = 260
        col2_lbl_x = 700
        col2_val_x = 800

        mx, my = pygame.mouse.get_pos()

        # ── Render Left Column (Game Settings) ─────────────────────────────
        for i, (label, options, is_dropdown) in enumerate(left_rows):
            y = start_y + i * row_h
            _render_text(screen, font_hdr, label, C.GRAYSCALE_UI["status_text"], (col1_lbl_x, y + 18))
            
            field_name = self._find_field(label, left_rows)

            if is_dropdown:
                # Render as single dropdown trigger
                active_opt = next((opt for opt in options if opt[2]), options[0])
                bw = 200
                bx = col1_val_x
                rect = pygame.Rect(bx, y + 4, bw, 32)
                hov = rect.collidepoint(mx, my) and not self._active_dropdown
                is_open = self._active_dropdown == field_name
                
                bg_col = C.GRAYSCALE_UI["menu_btn_hover"] if (hov or is_open) else C.GRAYSCALE_UI["menu_btn"]
                bdr_col = (220, 230, 240, 255) if is_open else ((200, 210, 220, 255) if hov else C.GRAYSCALE_UI["border"])
                
                pygame.draw.rect(screen, bg_col, rect, border_radius=5)
                pygame.draw.rect(screen, bdr_col, rect, width=2, border_radius=5)
                
                # Active option text left aligned, triangle right aligned
                lbl = font_val.render(active_opt[1], True, (255, 255, 255) if is_open else C.GRAYSCALE_UI["menu_btn_text"])
                screen.blit(lbl, (bx + 15, rect.centery - lbl.get_height() // 2))
                tri = font_val.render("▼", True, (200, 200, 200))
                screen.blit(tri, (bx + bw - 25, rect.centery - tri.get_height() // 2))
                
                self._clickables.append((field_name, "_dropdown_trigger", rect))
                
                if is_open:
                    dropdown_state_to_draw = (field_name, options, bx, y + 4 + 32, bw)
            else:
                # Render as horizontal toggle buttons
                for j, (opt_val, opt_label, active) in enumerate(options):
                    if label in ("OPPONENT AI", "NEUTRAL AI"):
                        bw = 68
                    elif label == "PLAYER COLOUR":
                        bw = 90
                    elif label == "GAME MODE":
                        bw = 100
                    else:
                        bw = 90
                    bx   = col1_val_x + j * (bw + 8)
                    rect = pygame.Rect(bx, y + 4, bw, 32)
                    hov  = rect.collidepoint(mx, my) and not self._active_dropdown
                    
                    btn_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                    bg_col   = C.GRAYSCALE_UI["menu_btn_hover"] if active else (C.GRAYSCALE_UI["menu_btn_hover"] if hov else C.GRAYSCALE_UI["menu_btn"])
                    bdr_col  = (220, 230, 240, 255) if active else ((200, 210, 220, 255) if hov else C.GRAYSCALE_UI["border"])
                    
                    pygame.draw.rect(btn_surf, bg_col, btn_surf.get_rect(), border_radius=5)
                    pygame.draw.rect(btn_surf, bdr_col, btn_surf.get_rect(), width=2, border_radius=5)
                    screen.blit(btn_surf, rect.topleft)
                    
                    tc   = (255, 255, 255) if active else ((240, 240, 245) if hov else C.GRAYSCALE_UI["menu_btn_text"])
                    _render_text(screen, font_val, opt_label, tc, rect.center)
    
                    self._clickables.append((field_name, opt_val, rect))

        # ── Render Right Column (Preferences) ──────────────────────────────
        for i, (label, options, is_dropdown) in enumerate(right_rows):
            y = start_y + i * row_h
            _render_text(screen, font_hdr, label, C.GRAYSCALE_UI["status_text"], (col2_lbl_x, y + 18))
            
            field_name = self._find_field(label, right_rows)

            if is_dropdown:
                # Render as single dropdown trigger
                active_opt = next((opt for opt in options if opt[2]), options[0])
                bw = 200
                bx = col2_val_x
                rect = pygame.Rect(bx, y + 4, bw, 32)
                hov = rect.collidepoint(mx, my) and not self._active_dropdown
                is_open = self._active_dropdown == field_name
                
                bg_col = C.GRAYSCALE_UI["menu_btn_hover"] if (hov or is_open) else C.GRAYSCALE_UI["menu_btn"]
                bdr_col = (220, 230, 240, 255) if is_open else ((200, 210, 220, 255) if hov else C.GRAYSCALE_UI["border"])
                
                pygame.draw.rect(screen, bg_col, rect, border_radius=5)
                pygame.draw.rect(screen, bdr_col, rect, width=2, border_radius=5)
                
                # Active option text left aligned, triangle right aligned
                lbl = font_val.render(active_opt[1], True, (255, 255, 255) if is_open else C.GRAYSCALE_UI["menu_btn_text"])
                screen.blit(lbl, (bx + 15, rect.centery - lbl.get_height() // 2))
                tri = font_val.render("▼", True, (200, 200, 200))
                screen.blit(tri, (bx + bw - 25, rect.centery - tri.get_height() // 2))
                
                self._clickables.append((field_name, "_dropdown_trigger", rect))
                
                if is_open:
                    dropdown_state_to_draw = (field_name, options, bx, y + 4 + 32, bw)
            else:
                # Render as horizontal toggle buttons
                for j, (opt_val, opt_label, active) in enumerate(options):
                    if label in ("SOUND FX", "MUSIC"):
                        bw = 60
                    else:
                        bw = 90
                    bx   = col2_val_x + j * (bw + 8)
                    rect = pygame.Rect(bx, y + 4, bw, 32)
                    hov  = rect.collidepoint(mx, my) and not self._active_dropdown
                    
                    btn_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                    bg_col   = C.GRAYSCALE_UI["menu_btn_hover"] if active else (C.GRAYSCALE_UI["menu_btn_hover"] if hov else C.GRAYSCALE_UI["menu_btn"])
                    bdr_col  = (220, 230, 240, 255) if active else ((200, 210, 220, 255) if hov else C.GRAYSCALE_UI["border"])
                    
                    pygame.draw.rect(btn_surf, bg_col, btn_surf.get_rect(), border_radius=5)
                    pygame.draw.rect(btn_surf, bdr_col, btn_surf.get_rect(), width=2, border_radius=5)
                    screen.blit(btn_surf, rect.topleft)
                    
                    tc   = (255, 255, 255) if active else ((240, 240, 245) if hov else C.GRAYSCALE_UI["menu_btn_text"])
                    _render_text(screen, font_val, opt_label, tc, rect.center)
    
                    self._clickables.append((field_name, opt_val, rect))

        # ── Bottom buttons ─────────────────────────────────────────────────
        by = 500
        for label, (action, color) in {
            "Save & Back": ("save", (60, 120, 60)),
            "Cancel":      ("cancel", (120, 60, 60)),
        }.items():
            bw, bh = 160, 42
            bx = cx + (-bw - 10 if action == "save" else 10)
            rect = pygame.Rect(bx, by, bw, bh)
            hov  = rect.collidepoint(mx, my)
            
            btn_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            bg_col   = C.GRAYSCALE_UI["menu_btn_hover"] if hov else C.GRAYSCALE_UI["menu_btn"]
            bdr_col  = (200, 210, 220, 255) if hov else C.GRAYSCALE_UI["border"]

            pygame.draw.rect(btn_surf, bg_col, btn_surf.get_rect(), border_radius=6)
            pygame.draw.rect(btn_surf, bdr_col, btn_surf.get_rect(), width=2, border_radius=6)
            screen.blit(btn_surf, rect.topleft)
            
            tc = (255, 255, 255) if hov else C.GRAYSCALE_UI["menu_btn_text"]
            _render_text(screen, font_btn, label, tc, rect.center)
            self._clickables.append((f"_btn_{action}", action, rect))
            
        # Draw floating popups on top
        if dropdown_state_to_draw:
            field_name, options, dx, dy, dw = dropdown_state_to_draw
            dh = len(options) * 32
            dd_rect = pygame.Rect(dx, dy, dw, dh)
            
            # Shadow and background
            pygame.draw.rect(screen, (10, 10, 10, 150), (dx+2, dy+2, dw, dh), border_radius=5)
            pygame.draw.rect(screen, C.GRAYSCALE_UI["panel_bg"], dd_rect, border_radius=5)
            pygame.draw.rect(screen, (200, 210, 220), dd_rect, width=1, border_radius=5)
            
            for k, (opt_val, opt_label, active) in enumerate(options):
                opt_rect = pygame.Rect(dx, dy + k * 32, dw, 32)
                hov = opt_rect.collidepoint(mx, my)
                if hov:
                    pygame.draw.rect(screen, C.GRAYSCALE_UI["menu_btn_hover"], opt_rect, border_radius=5)
                
                tc = (255, 255, 255) if (active or hov) else C.GRAYSCALE_UI["menu_btn_text"]
                lbl = font_val.render(opt_label, True, tc)
                screen.blit(lbl, (dx + 15, opt_rect.centery - lbl.get_height() // 2))
                
                self._dropdown_rects.append((field_name, opt_val, opt_rect))

    # ── Helpers ───────────────────────────────────────────────────────────

    def _find_field(self, label: str, rows) -> str:
        """Map row label back to GameConfig field name."""
        _MAP = {
            "GAME MODE":      "single_player",
            "PLAYER COLOUR":  "human_colour",
            "OPPONENT AI":    "opponent_ai",
            "NEUTRAL AI":     "neutral_ai",
            "TIME CONTROL":   "time_control",
            "THEME":          "theme",
            "INITIAL MAP":    "layout_file",
            "SOUND FX":       "sfx_volume",
            "MUSIC":          "music_volume",
            "RELAY SERVER":   "relay_server_url",
        }
        return _MAP.get(label, label)

    def _row_toggle(self, field: str, options: list[tuple]) -> list[tuple]:
        cur = getattr(self._cfg, field)
        return [(v, lbl, cur == v) for v, lbl in options]

    def _row_cycle(self, field: str, keys: list[str]) -> list[tuple]:
        cur = getattr(self._cfg, field)
        return [(k, k.title(), cur == k) for k in keys]

    def _row_cycle_tc(self, field: str, keys: list[str]) -> list[tuple]:
        from constants import TIME_CONTROLS
        cur = getattr(self._cfg, field)
        return [(k, TIME_CONTROLS[k]["name"], cur == k) for k in keys]

    def _row_cycle_relay(self, field: str, options: list[str]) -> list[tuple]:
        cur = getattr(self._cfg, field)
        friendly_names = {
            "wss://kings-trial-server.fly.dev": "Official Cloud",
            "ws://localhost:8765": "Local Server",
        }
        return [(opt, friendly_names.get(opt, opt), cur == opt) for opt in options]

    def _handle_click(self, field: str, value) -> AppState | None:
        if value == "_text_input" and field == "relay_server_url":
            return None

        if value == "_dropdown_trigger":
            self._active_dropdown = field if self._active_dropdown != field else None
            return None
            
        if field == "_btn_save":
            self._commit_relay_url()
            if self._relay_error:
                return None
            self.app.config = self._cfg
            self._cfg.save()
            log.info("Settings saved: %s", vars(self._cfg))
            
            import ui.audio
            ui.audio.update_settings(self.app.config.sfx_volume, self.app.config.music_volume)
            import ui.theme
            ui.theme.manager.load_theme(self.app.config.theme)
            
            return self._back()
        elif field == "_btn_cancel":
            return self._back()
        else:
            setattr(self._cfg, field, value)
            if field == "relay_server_url":
                self._relay_text = value
        return None

    # ── Relay URL text-input helpers ──────────────────────────────────────

    def _handle_relay_key(self, event: pygame.event.Event) -> AppState | None:
        """Handle key events while the relay URL field is active."""
        return None

    def _commit_relay_url(self) -> None:
        """Validate and apply the edited relay URL."""
        self._relay_error = ""

    def _cancel_relay_edit(self) -> None:
        """Revert the relay URL field to the last committed value."""
        self._relay_editing = False
        self._relay_error   = ""

    def _back(self) -> AppState | None:
        if isinstance(self.back_state, AppState):
            return self.back_state
        return AppState.MENU
