"""
ui/panels.py
============
Renders all UI panel elements OUTSIDE the chess board for King's Trial.

Responsibilities:
  - Top bar: 3 clocks (White, Neutral, Black) + 2 score panels
  - Bottom section:
      • 4-column move log (White | White-Neutral | Black | Black-Neutral)
      • Game status bar (current phase, turn number, active player)
      • Menu buttons (Pause / Resume, Restart)

All functions accept a Pygame surface, a theme dict, and relevant data dicts.
They hold NO game state — data is passed in from game_state.py at runtime.
"""

import pygame
from constants import (
    WINDOW_W, WINDOW_H,
    BOARD_RANKS, BOARD_COLS, SQUARE_SIZE,
    PANEL_TOP_H, PANEL_BOTTOM_H, SIDE_LABEL_W, FILE_LABEL_H,
    PHASE_NAMES, PHASE_WHITE, PHASE_BLACK,
    FONT_SIZE_TIMER, FONT_SIZE_SCORE, FONT_SIZE_LOG,
    MAX_CYCLES,
    FONT_SIZE_STATUS, FONT_SIZE_BTN, FONT_SIZE_UI,
    PIECE_COLOR_WHITE, PIECE_COLOR_BLACK, PIECE_COLOR_NEUTRAL,
    GRAYSCALE_UI,
    PIECE_VALUES, PROMOTION_COST, MAX_PIECE_LIMITS,
    log,
)

# ---------------------------------------------------------------------------
# Font cache
# ---------------------------------------------------------------------------

_fonts: dict = {}

def _font(key: str, size: int, bold: bool = False) -> pygame.font.Font:
    cache_key = (key, size, bold)
    if cache_key not in _fonts:
        _fonts[cache_key] = pygame.font.SysFont("dejavusansmono", size, bold=bold)
    return _fonts[cache_key]


# ---------------------------------------------------------------------------
# Layout constants (computed from window geometry)
# ---------------------------------------------------------------------------

BOARD_AREA_TOP = PANEL_TOP_H + FILE_LABEL_H
BOARD_AREA_H   = BOARD_COLS * SQUARE_SIZE
BOARD_AREA_W   = BOARD_RANKS * SQUARE_SIZE

BOTTOM_AREA_TOP = BOARD_AREA_TOP + BOARD_AREA_H + FILE_LABEL_H  # y start of bottom panel
BOTTOM_AREA_H   = PANEL_BOTTOM_H

# Horizontal extent of the board (including side gutters)
FULL_BOARD_W = SIDE_LABEL_W + BOARD_AREA_W + SIDE_LABEL_W   # = WINDOW_W


# ---------------------------------------------------------------------------
# Helper: draw a filled rounded rectangle (simple version via multiple rects)
# ---------------------------------------------------------------------------

def _draw_panel_bg(surface: pygame.Surface, rect: pygame.Rect, color: tuple) -> None:
    """Draw a filled background rectangle."""
    pygame.draw.rect(surface, color, rect, border_radius=6)


def _text(surface, font, text, color, center):
    """Render antialiased text centred on a point."""
    lbl = font.render(text, True, color)
    surface.blit(lbl, lbl.get_rect(center=center))


# ---------------------------------------------------------------------------
# Background fills
# ---------------------------------------------------------------------------

def draw_backgrounds(surface: pygame.Surface) -> None:
    """Fill the top panel and bottom panel with theme background colours."""
    # Top panel
    top_rect = pygame.Rect(0, 0, WINDOW_W, PANEL_TOP_H)
    pygame.draw.rect(surface, GRAYSCALE_UI["panel_bg"], top_rect)

    # Bottom panel
    bot_rect = pygame.Rect(0, BOTTOM_AREA_TOP, WINDOW_W, BOTTOM_AREA_H)
    pygame.draw.rect(surface, GRAYSCALE_UI["panel_bg"], bot_rect)

    # Window background (fills gaps between board and panels)
    surface.fill(GRAYSCALE_UI["bg"])
    # Re-fill panels on top of the bg fill
    pygame.draw.rect(surface, GRAYSCALE_UI["panel_bg"], top_rect)
    pygame.draw.rect(surface, GRAYSCALE_UI["panel_bg"], bot_rect)


# ---------------------------------------------------------------------------
# Top panel: Timers + Scores
# Layout (L→R):  [White Timer] [White Score] [Neutral Timer] [Black Score] [Black Timer]
# ---------------------------------------------------------------------------

# Approximate column centres for the 5 top-bar widgets
def _top_bar_centres() -> list[int]:
    """Return 5 evenly-spaced x-centres across the window."""
    step = WINDOW_W // 6
    return [step * i for i in range(1, 6)]


def draw_top_bar(
    surface: pygame.Surface,
    white_time: float,
    neutral_time: float,
    black_time: float,
    white_score: int,
    black_score: int,
    active_phase: int,
) -> None:
    """
    Draw the top information bar.

    time values are in seconds (float).
    active_phase: which phase is currently running (for clock highlight).
    """
    centres = _top_bar_centres()
    panel_h  = PANEL_TOP_H - 10
    panel_y  = 5
    panel_w  = WINDOW_W // 6 - 10

    # Black panel header colour: use a clear light grey so it's readable on the
    # dark timer background — matches what the user's eye expects for "B-PTS" consistency.
    _BLACK_LABEL_COLOR = (200, 200, 200)

    labels_and_data = [
        # (x_centre, header, value_str, header_colour, bg_key)
        (centres[0], "WHITE",   _fmt_time(white_time),   PIECE_COLOR_WHITE,    "timer_white_bg"),
        (centres[1], "W-PTS",   str(white_score),        PIECE_COLOR_WHITE,    "timer_white_bg"),
        (centres[2], "NEUTRAL", _fmt_time(neutral_time), (200, 200, 200),      "timer_neutral_bg"),
        (centres[3], "B-PTS",   str(black_score),        _BLACK_LABEL_COLOR,   "timer_black_bg"),
        (centres[4], "BLACK",   _fmt_time(black_time),   _BLACK_LABEL_COLOR,   "timer_black_bg"),
    ]

    tfont  = _font("timer", FONT_SIZE_TIMER, bold=True)
    hfont  = _font("hdr",   FONT_SIZE_UI,   bold=True)

    for (cx, header, value, hcolor, bg_key) in labels_and_data:
        rect = pygame.Rect(cx - panel_w // 2, panel_y, panel_w, panel_h)
        _draw_panel_bg(surface, rect, GRAYSCALE_UI[bg_key])

        # Header label
        _text(surface, hfont, header, hcolor, (cx, panel_y + 14))
        # Value (timer or score)
        _text(surface, tfont, value, GRAYSCALE_UI["panel_text"], (cx, panel_y + 14 + 28))


def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    seconds = max(0.0, seconds)
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Bottom panel layout
# ---------------------------------------------------------------------------
#
#  ┌──────────────────────────────────────────────────────────────────────┐
#  │   MOVE LOG (4 columns)   │  STATUS BAR  │  MENU BUTTONS            │
#  └──────────────────────────────────────────────────────────────────────┘
#
MOVE_LOG_W   = int(WINDOW_W * 0.60)   # 60 % of window width
STATUS_W     = int(WINDOW_W * 0.24)   # 24 %
MENU_W       = WINDOW_W - MOVE_LOG_W - STATUS_W  # remaining ~16 %

MOVE_LOG_X   = 0
STATUS_X     = MOVE_LOG_X + MOVE_LOG_W
MENU_X       = STATUS_X + STATUS_W

LOG_ROW_H    = 16    # height of one move log row
LOG_HEADER_H = 20    # height of column header row


def draw_bottom_panel(
    surface: pygame.Surface,
    move_log: list[dict],
    current_phase: int,
    move_number: int,
    game_status_msg: str,
    paused: bool,
    scroll_index: int = 0,
    selected_piece: dict | None = None,
    player_points: int = 0,
    respawn_pool: list[dict] = None,
    owner: str = "white",
    piece_counts: dict[str, int] = None,
    online_mode: bool = False,
) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect, dict[str, tuple[str, pygame.Rect]]]:
    """
    Draw the full bottom panel.

    move_log: list of dicts, each representing one full cycle:
        { 'w': 'e4', 'wn': 'Nf6', 'b': 'd5', 'bn': 'Bb5' }
        Empty string '' means no move was recorded for that phase.

    Returns (pause_btn_rect, restart_btn_rect) for click detection in main.py.
    """
    base_y = BOTTOM_AREA_TOP

    # ---- move log ----
    sb_track, _ = _draw_move_log(surface, move_log, base_y, scroll_index)

    # ---- status bar ----
    action_btns = _draw_status_bar(surface, current_phase, move_number, game_status_msg, base_y, selected_piece, player_points, respawn_pool, owner, piece_counts)

    # ---- menu buttons ----
    pause_btn, restart_btn = _draw_menu(surface, paused, base_y, online_mode=online_mode)

    return pause_btn, restart_btn, sb_track, action_btns


def _draw_move_log(
    surface: pygame.Surface,
    move_log: list[dict],
    base_y: int,
    scroll_index: int = 0,
) -> tuple[pygame.Rect, pygame.Rect]:
    """
    Draw the 4-column move log with a scrollbar.
    scroll_index: index of the first visible row from the end (0 = show tail).
    """
    log_rect = pygame.Rect(MOVE_LOG_X, base_y, MOVE_LOG_W, BOTTOM_AREA_H)
    pygame.draw.rect(surface, GRAYSCALE_UI["move_log_bg"], log_rect)

    hfont = _font("loghdr", FONT_SIZE_LOG, bold=True)
    rfont = _font("logrow", FONT_SIZE_LOG)

    col_w    = MOVE_LOG_W // 4   # 4 virtual cols: move#, W, Neutral, B
    headers  = ["#", "White", "Neutral", "Black"]
    hcolours = [
        GRAYSCALE_UI["move_log_header"],
        PIECE_COLOR_WHITE,
        (200, 200, 200),
        (180, 180, 200),
    ]
    
    # ── Header ────────────────────────────────────────────────────────────
    for i, hdr in enumerate(headers):
        cx = MOVE_LOG_X + col_w * i + col_w // 2
        cy = base_y + LOG_HEADER_H // 2
        _text(surface, hfont, hdr, hcolours[i], (cx, cy))

    pygame.draw.line(
        surface, GRAYSCALE_UI["move_log_header"],
        (MOVE_LOG_X, base_y + LOG_HEADER_H),
        (MOVE_LOG_X + MOVE_LOG_W, base_y + LOG_HEADER_H), 1
    )

    # ── Rows ──────────────────────────────────────────────────────────────
    visible_rows = (BOTTOM_AREA_H - LOG_HEADER_H) // LOG_ROW_H - 1 # slack for spacing
    
    # Calculate slice
    max_scroll = max(0, len(move_log) - visible_rows)
    actual_scroll = max(0, min(scroll_index, max_scroll))
    
    # We display moves from (len - visible - actual_scroll) to (len - actual_scroll)
    start_idx = max(0, len(move_log) - visible_rows - actual_scroll)
    end_idx   = len(move_log) - actual_scroll
    display_log = move_log[start_idx:end_idx]

    for row_i, entry in enumerate(display_log):
        y = base_y + LOG_HEADER_H + row_i * LOG_ROW_H + LOG_ROW_H // 2 + 5
        # Alternating row tint (darker band for contrast against log text)
        if row_i % 2 == 0:
            row_rect = pygame.Rect(MOVE_LOG_X, y - LOG_ROW_H // 2, MOVE_LOG_W, LOG_ROW_H)
            pygame.draw.rect(surface, (0, 0, 0, 30), row_rect)

        cells = [
            str(entry.get("cycle", row_i + start_idx + 1)),
            entry.get("w",  ""),
            entry.get("wn", ""),
            entry.get("b",  ""),
        ]
        for i, cell in enumerate(cells):
            cx = MOVE_LOG_X + col_w * i + col_w // 2
            _text(surface, rfont, cell, GRAYSCALE_UI["move_log_text"], (cx, y))

    # ── Scrollbar ─────────────────────────────────────────────────────────
    # Draw simple vertical scrollbar on the far right of the log panel
    sb_w = 6
    sb_x = MOVE_LOG_X + MOVE_LOG_W - sb_w - 4
    sb_y = base_y + LOG_HEADER_H + 4
    sb_h = BOTTOM_AREA_H - LOG_HEADER_H - 8
    
    track_rect = pygame.Rect(sb_x, sb_y, sb_w, sb_h)
    pygame.draw.rect(surface, (40, 40, 40), track_rect, border_radius=3)
    
    if len(move_log) > visible_rows:
        # Calculate handle size and pos
        fraction   = visible_rows / len(move_log)
        handle_h   = max(20, int(sb_h * fraction))
        
        # Pos depends on actual_scroll (which is distance from the end)
        # 0 scroll = bottom, max_scroll = top
        scroll_ratio = actual_scroll / max_scroll
        handle_y = sb_y + (sb_h - handle_h) * (1.0 - scroll_ratio)
        
        handle_rect = pygame.Rect(sb_x, handle_y, sb_w, handle_h)
        pygame.draw.rect(surface, GRAYSCALE_UI["move_log_header"], handle_rect, border_radius=3)

    return track_rect, pygame.Rect(0, 0, 0, 0) # Dummy rects for compatibility


def _draw_status_bar(
    surface: pygame.Surface,
    current_phase: int,
    move_number: int,
    game_status_msg: str,
    base_y: int,
    selected_piece: dict | None = None,
    player_points: int = 0,
    respawn_pool: list[dict] = None,
    owner: str = "white",
    piece_counts: dict[str, int] = None,
) -> dict[str, tuple[str, pygame.Rect]]:
    """Draw phase name, move number, and any game-status messages."""
    rect = pygame.Rect(STATUS_X, base_y, STATUS_W, BOTTOM_AREA_H)
    pygame.draw.rect(surface, GRAYSCALE_UI["panel_bg"], rect)
    # Draw border on left side of status area
    pygame.draw.line(surface, GRAYSCALE_UI["border"],
                     (STATUS_X, base_y), (STATUS_X, base_y + BOTTOM_AREA_H), 1)

    sfont  = _font("status", FONT_SIZE_STATUS, bold=True)
    sfont2 = _font("status2", FONT_SIZE_UI)

    cx = STATUS_X + STATUS_W // 2

    # Move number
    _text(surface, sfont2, f"Cycle  {move_number} / {MAX_CYCLES}",
          GRAYSCALE_UI["status_text"], (cx, base_y + 20))

    # Phase name
    phase_name = PHASE_NAMES.get(current_phase, "---")
    _text(surface, sfont, phase_name,
          GRAYSCALE_UI["status_text"], (cx, base_y + 50))

    # Game status message (win, draw, etc.)
    if game_status_msg:
        msg_font = _font("gmsg", FONT_SIZE_STATUS, bold=True)
        _text(surface, msg_font, game_status_msg,
              (220, 80, 80), (cx, base_y + 90))

    # Action Buttons
    action_rects = {}
    btn_w, btn_h = 44, 44
    gap = 8
    total_w = 5 * btn_w + 4 * gap
    start_x = cx - total_w // 2
    btn_y = base_y + 130

    is_king = selected_piece and selected_piece["type"] == "K"
    is_owned = selected_piece and selected_piece["owner"] == owner
    
    available_respawns = set()
    if respawn_pool:
        available_respawns = {p["type"] for p in respawn_pool if p["type"] != "K"}
    available_respawns.add("P")

    current_val = PIECE_VALUES.get(selected_piece["type"], 0) if (selected_piece and not is_king) else 0
    font_sub = _font("sub", 10)
    
    for i, ptype in enumerate(["P", "N", "B", "R", "Q"]):
        rect = pygame.Rect(start_x + i * (btn_w + gap), btn_y, btn_w, btn_h)
        affordable = False
        action = None
        cost_str = ""
        cost_color = (150, 150, 150)
        
        limit_reached = False
        if piece_counts and ptype in ("N", "B", "R", "Q"):
            if piece_counts.get(ptype, 0) >= MAX_PIECE_LIMITS.get(ptype, 99):
                limit_reached = True

        pval = PIECE_VALUES.get(ptype, 0)

        if is_owned:
            if is_king:
                if ptype in available_respawns:
                    cost = pval
                    if player_points >= cost and not limit_reached:
                        affordable = True
                        action = "respawn"
                        cost_str = f"-{cost}"
                        cost_color = PIECE_COLOR_WHITE if owner == "white" else (230, 210, 160)
                    elif limit_reached:
                        cost_str = "MAX"
                    else:
                        cost_str = f"-{cost}"
            else:
                if ptype != selected_piece["type"]:
                    if pval > current_val:
                        cost = PROMOTION_COST.get(ptype, 99)
                        if player_points >= cost and not limit_reached:
                            affordable = True
                            action = "promote"
                            cost_str = f"-{cost}"
                            cost_color = PIECE_COLOR_WHITE if owner == "white" else (230, 210, 160)
                        elif limit_reached:
                            cost_str = "MAX"
                        else:
                            cost_str = f"-{cost}"
                    elif pval < current_val and selected_piece["type"] not in ("K", "P"):
                        refund = current_val - pval
                        affordable = True
                        action = "demote"
                        cost_str = f"+{refund}"
                        cost_color = (160, 230, 160) if owner == "white" else (120, 200, 120)

        mx, my = pygame.mouse.get_pos()
        hov = rect.collidepoint(mx, my) and affordable
        
        import ui.theme
        import assets as _assets_mod
        from ui.renderer import _piece_display, _get_font
        display_owner = owner if owner in ("white", "black", "neutral") else "white"
        letter, lcolor, badge_color, border_color = _piece_display(ptype, display_owner)
        
        cfg_owner = ui.theme.manager.current_theme["pieces"].get(display_owner, ui.theme.manager.current_theme["pieces"]["white"])
        font = _get_font(f"piece_{display_owner}", cfg_owner["font_size"])

        if affordable:
            bg_color = cfg_owner.get("highlight", GRAYSCALE_UI["menu_btn_hover"]) if hov else badge_color
        else:
            bg_color = (30, 32, 36)
            
        badge_rect = rect.inflate(-4, -4)
        pygame.draw.rect(surface, bg_color, badge_rect, border_radius=3)
        
        if border_color and affordable:
            pygame.draw.rect(surface, border_color, badge_rect, width=2, border_radius=3)
        elif hov and affordable:
            pygame.draw.rect(surface, (255, 255, 255), badge_rect, width=2, border_radius=3)

        # Try to draw piece sprite; fall back to letter
        am = _assets_mod.AssetManager.instance()
        sprite = am.get_piece_sprite(display_owner, ptype)
        if sprite is not None:
            btn_inner = badge_rect.inflate(-6, -6)
            sprite_size = min(btn_inner.width, btn_inner.height)
            scaled = pygame.transform.smoothscale(sprite, (sprite_size, sprite_size))
            if not affordable:
                # Dim the sprite for unavailable actions
                dimmed = scaled.copy()
                dimmed.fill((0, 0, 0, 160), special_flags=pygame.BLEND_RGBA_MULT)
                scaled = dimmed
            surface.blit(scaled, scaled.get_rect(center=rect.center))
        else:
            if not affordable:
                lcolor = (80, 80, 80)
            lbl = font.render(letter, True, lcolor)
            surface.blit(lbl, lbl.get_rect(center=rect.center))
        
        if is_owned and (cost_str or action):
            _text(surface, font_sub, cost_str, cost_color, (rect.centerx, rect.bottom + 10))
            
        if affordable and action:
            action_rects[ptype] = (action, rect)

    return action_rects



def _draw_menu(
    surface: pygame.Surface,
    paused: bool,
    base_y: int,
    online_mode: bool = False,
) -> tuple[pygame.Rect, pygame.Rect]:
    """
    Draw Pause/Resume and Restart buttons.
    In online_mode: Pause is greyed-out/disabled; End Game is labelled FORFEIT.
    Returns (pause_btn_rect, restart_btn_rect) for click detection.
    """
    rect = pygame.Rect(MENU_X, base_y, MENU_W, BOTTOM_AREA_H)
    pygame.draw.rect(surface, GRAYSCALE_UI["panel_bg"], rect)
    pygame.draw.line(surface, GRAYSCALE_UI["border"],
                     (MENU_X, base_y), (MENU_X, base_y + BOTTOM_AREA_H), 1)

    bfont = _font("btn", FONT_SIZE_BTN, bold=True)
    cx    = MENU_X + MENU_W // 2
    btn_w = MENU_W - 20
    btn_h = 34

    mx, my = pygame.mouse.get_pos()

    # Pause / Resume button
    if online_mode:
        # Greyed-out in online mode — clicking has no effect (handled in OnlineGameplayScene)
        pause_label = "PAUSE (N/A)"
        pause_rect  = pygame.Rect(cx - btn_w // 2, base_y + 25, btn_w, btn_h)
        pygame.draw.rect(surface, (35, 35, 40), pause_rect, border_radius=6)
        _text(surface, bfont, pause_label, (80, 80, 90), pause_rect.center)
    else:
        pause_label = "RESUME" if paused else "PAUSE"
        pause_rect  = pygame.Rect(cx - btn_w // 2, base_y + 25, btn_w, btn_h)
        p_hov = pause_rect.collidepoint(mx, my)
        pygame.draw.rect(surface, GRAYSCALE_UI["menu_btn_hover"] if p_hov else GRAYSCALE_UI["menu_btn"], pause_rect, border_radius=6)
        if p_hov:
            pygame.draw.rect(surface, GRAYSCALE_UI["border"], pause_rect, width=2, border_radius=6)
        _text(surface, bfont, pause_label, (255, 255, 255) if p_hov else GRAYSCALE_UI["menu_btn_text"],
              pause_rect.center)

    # End Game / Forfeit button
    end_label = "FORFEIT" if online_mode else "END GAME"
    restart_rect = pygame.Rect(cx - btn_w // 2, base_y + 70, btn_w, btn_h)
    r_hov = restart_rect.collidepoint(mx, my)
    # In online mode use a warm amber tint to signal 'danger' action
    if online_mode:
        btn_bg  = (120, 55, 10) if r_hov else (80, 35, 8)
        btn_fg  = (255, 200, 120) if r_hov else (200, 140, 80)
    else:
        btn_bg  = GRAYSCALE_UI["menu_btn_hover"] if r_hov else GRAYSCALE_UI["menu_btn"]
        btn_fg  = (255, 255, 255) if r_hov else GRAYSCALE_UI["menu_btn_text"]
    pygame.draw.rect(surface, btn_bg, restart_rect, border_radius=6)
    if r_hov:
        pygame.draw.rect(surface, GRAYSCALE_UI["border"], restart_rect, width=2, border_radius=6)
    _text(surface, bfont, end_label, btn_fg, restart_rect.center)

    return pause_rect, restart_rect
