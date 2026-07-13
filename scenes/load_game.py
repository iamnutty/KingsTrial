"""
scenes/load_game.py
===================
LoadGameScene — browse and load a .kgt save file.

Lists all KingsTrial_*.kgt files in the current working directory,
sorted newest-first. Player clicks a file → snapshot is parsed and
loaded into GameplayScene → transitions to GAMEPLAY.

If no files are found, a "No save files found" message is shown.
Press Escape / Back to return to the caller (menu or pause).
"""

from __future__ import annotations
import os
import glob
import logging
import pygame

from scenes.base_scene import Scene, AppState

log = logging.getLogger("KingsTrial.load_game")

_BG     = ( 18,  20,  30)
_PANEL  = ( 28,  32,  48)
_BORDER = ( 80,  90, 130)
_GOLD   = (255, 215,  60)
_FG     = (200, 210, 230)
_DIM    = ( 80,  90, 110)
_ERR    = (200,  70,  70)
_OK     = ( 70, 200, 120)


from record_saver import _SAVE_DIR


def _find_saves(directory: str | None = None) -> list[str]:
    """Return all .kgt files sorted newest-first."""
    if directory is None:
        directory = _SAVE_DIR
    pattern = os.path.join(directory, "*.kgt")
    files   = sorted(glob.glob(pattern), reverse=True)
    return files


class LoadGameScene(Scene):
    """File-picker scene for loading a saved game."""

    VISIBLE_ROWS = 10      # max files shown at once
    ROW_H        = 46

    def __init__(self, app, screen: pygame.Surface,
                 back_state: AppState = AppState.MENU) -> None:
        self.app        = app
        self.screen     = screen
        self.back_state = back_state

        self._files:     list[str]  = []
        self._scroll:    int        = 0
        self._selected:  int | None = None
        self._message:   str        = ""
        self._msg_color              = _FG
        self._row_rects: list[tuple[int, pygame.Rect]] = []

    def on_enter(self, prev_state: AppState | None = None) -> None:
        pygame.display.set_caption("King's Trial  ♟  Load Game")
        self._files    = _find_saves()
        self._scroll   = 0
        self._selected = None
        self._message  = "" if self._files else "No save files found in current directory."
        self._msg_color = _ERR if not self._files else _FG
        log.debug("LoadGameScene: found %d save files", len(self._files))

    # ── Scene interface ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> AppState | None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                return self.back_state
            elif event.key == pygame.K_RETURN and self._selected is not None:
                return self._load(self._selected)
            elif event.key == pygame.K_UP:
                self._selected = max(0, (self._selected or 0) - 1)
                self._scroll_to(self._selected)
            elif event.key == pygame.K_DOWN:
                n = len(self._files)
                self._selected = min(n - 1, (self._selected or 0) + 1)
                self._scroll_to(self._selected)

        elif event.type == pygame.MOUSEWHEEL:
            self._scroll = max(0, min(
                self._scroll - event.y,
                max(0, len(self._files) - self.VISIBLE_ROWS)
            ))

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            for idx, rect in self._row_rects:
                if rect.collidepoint(mx, my):
                    if self._selected == idx:
                        return self._load(idx)   # double-click = load
                    self._selected = idx
                    return None
            # Check Back button
            if hasattr(self, "_back_rect") and self._back_rect.collidepoint(mx, my):
                return self.back_state
            # Check Load button
            if hasattr(self, "_load_rect") and self._load_rect.collidepoint(mx, my):
                if self._selected is not None:
                    return self._load(self._selected)

        return None

    def update(self, dt: float) -> AppState | None:
        return None

    def render(self, screen: pygame.Surface) -> None:
        screen.fill(_BG)
        W, H = screen.get_size()
        cx = W // 2

        font_ttl  = pygame.font.SysFont("dejavusansmono", 26, bold=True)
        font_row  = pygame.font.SysFont("dejavusansmono", 14)
        font_med  = pygame.font.SysFont("dejavusansmono", 14)
        font_btn  = pygame.font.SysFont("dejavusansmono", 15, bold=True)

        # Title
        lbl = font_ttl.render("Load Game", True, _GOLD)
        screen.blit(lbl, lbl.get_rect(center=(cx, 44)))

        # Message (error / info)
        if self._message:
            ml = font_med.render(self._message, True, self._msg_color)
            screen.blit(ml, ml.get_rect(center=(cx, 85)))

        # File list
        list_x = cx - 340
        list_y = 110
        list_w = 680

        self._row_rects = []
        visible = self._files[self._scroll: self._scroll + self.VISIBLE_ROWS]

        for i, path in enumerate(visible):
            idx   = self._scroll + i
            y     = list_y + i * self.ROW_H
            rect  = pygame.Rect(list_x, y, list_w, self.ROW_H - 4)
            sel   = (idx == self._selected)

            bg  = (70, 75, 80) if sel else ((45, 48, 52) if i % 2 == 0 else (35, 38, 42))
            bdr = _GOLD if sel else (100, 105, 110)
            pygame.draw.rect(screen, bg, rect, border_radius=4)
            pygame.draw.rect(screen, bdr, rect, width=1, border_radius=4)

            # Filename (without dir)
            fname = os.path.basename(path)
            # Try to parse date/time from filename: {prefix}_YYYYMMDD_HHMMSS.kgt
            try:
                bare   = fname.replace(".kgt", "")
                parts  = bare.rsplit("_", 2)   # split off last two tokens
                d, t   = parts[-2], parts[-1]
                name   = "_".join(parts[:-2]) if len(parts) > 2 else bare
                pretty = f"{name}  —  {d[:4]}-{d[4:6]}-{d[6:8]}  {t[:2]}:{t[2:4]}:{t[4:6]}"
            except (IndexError, ValueError):
                pretty = fname

            # Also show file size
            try:
                sz = os.path.getsize(path)
                size_str = f"{sz / 1024:.1f} KB"
            except OSError:
                size_str = ""

            tc  = _GOLD if sel else _FG
            lbl = font_row.render(pretty, True, tc)
            screen.blit(lbl, (rect.x + 12, rect.centery - lbl.get_height() // 2))

            sz_lbl = font_row.render(size_str, True, _DIM)
            screen.blit(sz_lbl, (rect.right - sz_lbl.get_width() - 12,
                                  rect.centery - sz_lbl.get_height() // 2))

            self._row_rects.append((idx, rect))

        # Scroll indicator
        if len(self._files) > self.VISIBLE_ROWS:
            total_h = self.VISIBLE_ROWS * self.ROW_H
            ratio   = self.VISIBLE_ROWS / len(self._files)
            bar_h   = max(20, int(total_h * ratio))
            bar_y   = list_y + int((self._scroll / (len(self._files) - self.VISIBLE_ROWS))
                                   * (total_h - bar_h))
            pygame.draw.rect(screen, (80, 90, 130),
                             pygame.Rect(list_x + list_w + 6, bar_y, 5, bar_h),
                             border_radius=3)

        # Bottom buttons
        by = list_y + self.VISIBLE_ROWS * self.ROW_H + 16
        btn_pairs = [
            ("← Back", "back", (cx - 180, by), _BORDER),
            ("Load ↵",  "load", (cx + 20,  by), (60, 130, 60) if self._selected is not None else (40, 60, 40)),
        ]
        mx, my = pygame.mouse.get_pos()
        for label, key, (bx, _by), color in btn_pairs:
            rect = pygame.Rect(bx, _by, 150, 40)
            
            hovered = rect.collidepoint(mx, my)
            btn_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            bg_alpha = 220 if hovered else 180
            bg_col   = (75, 80, 85, bg_alpha) if hovered else (40, 42, 45, bg_alpha)
            bdr_col  = (200, 210, 220, 255) if hovered else (100, 105, 110, 200)

            pygame.draw.rect(btn_surf, bg_col, btn_surf.get_rect(), border_radius=6)
            pygame.draw.rect(btn_surf, bdr_col, btn_surf.get_rect(), width=2, border_radius=6)
            screen.blit(btn_surf, rect.topleft)
            
            tc = (255, 255, 255) if hovered else (200, 210, 220)
            l = font_btn.render(label, True, tc)
            screen.blit(l, l.get_rect(center=rect.center))
            if key == "back":
                self._back_rect = rect
            else:
                self._load_rect = rect

        # Hint
        hint = font_med.render("Click once to select · double-click or ↵ to load · ↑↓ to navigate",
                               True, _DIM)
        screen.blit(hint, hint.get_rect(center=(cx, H - 24)))

    # ── Internal ──────────────────────────────────────────────────────────

    def _scroll_to(self, idx: int) -> None:
        if idx < self._scroll:
            self._scroll = idx
        elif idx >= self._scroll + self.VISIBLE_ROWS:
            self._scroll = idx - self.VISIBLE_ROWS + 1

    def _load(self, idx: int) -> AppState | None:
        from record_saver import load_state_snapshot, parse_move_log
        path = self._files[idx]
        snap = load_state_snapshot(path)
        if snap is None:
            self._message   = f"Could not parse snapshot from: {os.path.basename(path)}"
            self._msg_color = _ERR
            log.warning("LoadGame: no snapshot in %s", path)
            return None

        # Restore configuration if present
        if "config" in snap and snap["config"]:
            try:
                from config import GameConfig
                loaded_cfg = GameConfig(**snap["config"])
                self.app.config = loaded_cfg
                
                # Rebuild GameplayScene and dependencies to apply new config
                from scenes.gameplay import GameplayScene
                from scenes.pause import PauseScene
                from scenes.confirm import ConfirmRestartScene
                from scenes.game_over import GameOverScene
                
                self.app._gameplay = GameplayScene(self.app.config, self.screen)
                self.app._scenes[AppState.GAMEPLAY] = self.app._gameplay
                self.app._scenes[AppState.PAUSED]   = PauseScene(self.app._gameplay, self.screen)
                self.app._scenes[AppState.CONFIRM_RESTART] = ConfirmRestartScene(self.app._gameplay, self.screen)
                self.app._scenes[AppState.GAME_OVER] = GameOverScene(self.app._gameplay, self.screen)
                log.info("LoadGame: Rebuilt scenes with saved config")
            except Exception as e:
                log.error("Failed to restore config from save file: %s", e)

        # Apply to the gameplay scene's GameState
        gameplay = self.app._gameplay
        gameplay.gs.restore_from_snapshot(snap)

        # Restore move log from the text table section
        move_log = parse_move_log(path)
        if move_log:
            gameplay.gs.move_log           = move_log[:-1]  # all but last cycle
            gameplay.gs._current_log_entry = move_log[-1]   # last cycle as working entry
        # (if empty, move_log stays at the blank state set by restore_from_snapshot)

        # Reset GameplayScene UI (clear dialogs, AI state, etc.)
        gameplay.scroll_index       = 0
        gameplay.active_dialog      = None
        gameplay.dialog_sq          = None
        gameplay.dialog_options     = {}
        gameplay.respawn_piece_type = None
        gameplay.respawn_targets    = []
        gameplay.ai_state           = 0
        gameplay.ai_timer           = 0.0
        gameplay.ai_move_data       = None
        gameplay.phase_delay_timer  = 0.0
        gameplay.saved_path         = path   # remember what was loaded

        self._message   = f"Loaded: {os.path.basename(path)}"
        self._msg_color = _OK
        log.info("LoadGame: restored from %s (game_over=%s)", path, snap.get("game_over"))

        # Route to GAME_OVER overlay if the save is a completed game,
        # otherwise resume normal gameplay
        if snap.get("game_over"):
            return AppState.GAME_OVER
        return AppState.GAMEPLAY
