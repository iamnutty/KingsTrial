"""
ui/renderer.py
==============
Handles all board-related drawing for King's Trial.

Responsibilities:
  - Draw the 8×26 board (oriented horizontally: ranks along X, files along Y)
  - Overlay restricted-rank zones (ranks 1–3 whited out, 24–26 greyed out)
  - Draw rank numbers and file letters in the gutters
  - Draw piece letters centred in their squares (with a badge background)
  - Draw selection highlights and valid-move dots
  - Apply a fog-of-war overlay outside the active 8×8 sub-board

All drawing functions accept a Pygame surface.
They do NOT hold any game state themselves — that comes in as parameters.
"""

import math
import pygame
import constants as C
import ui.theme
from constants import (
    BOARD_COLS, BOARD_RANKS, SQUARE_SIZE,
    PANEL_TOP_H, FILE_LABEL_H, SIDE_LABEL_W,
    FONT_SIZE_PIECE, FONT_SIZE_LABEL,
    log,
)


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def board_to_pixel(rank: int, col: int) -> tuple[int, int]:
    """
    Convert a board (rank, col) — both 1-indexed — to the top-left pixel
    of that square on screen.

    The board is rendered horizontally:
      - rank increases left → right  (rank 1 is leftmost)
      - col  increases top  → bottom (col 1 = file A is topmost)

    Returns (x, y) pixel position of top-left corner of the square.
    """
    x = SIDE_LABEL_W + (rank - 1) * SQUARE_SIZE
    y = PANEL_TOP_H + FILE_LABEL_H + (col - 1) * SQUARE_SIZE
    return x, y


def pixel_to_board(px: int, py: int) -> tuple[int, int] | None:
    """
    Convert a screen pixel (px, py) to (rank, col) — both 1-indexed.
    Returns None if the pixel is outside the board area.
    """
    x = px - SIDE_LABEL_W
    y = py - PANEL_TOP_H - FILE_LABEL_H

    if x < 0 or y < 0:
        return None
    rank = x // SQUARE_SIZE + 1
    col  = y // SQUARE_SIZE + 1
    if 1 <= rank <= BOARD_RANKS and 1 <= col <= BOARD_COLS:
        return rank, col
    return None


# ---------------------------------------------------------------------------
# Font cache (populated once after pygame.font.init())
# ---------------------------------------------------------------------------

_fonts: dict = {}

def clear_font_cache() -> None:
    """Clear cached fonts so new themes can load their specific fonts."""
    _fonts.clear()

def _get_font(key: str, size: int) -> pygame.font.Font:
    """Lazy-load and cache a system font or custom font per owner."""
    if key not in _fonts:
        if key.startswith("piece_"):
            owner = key.split("_")[1]
            try:
                font_file = ui.theme.manager.current_theme["pieces"][owner]["font_file"]
            except KeyError:
                font_file = "system"
                
            if font_file and font_file.lower() != "system":
                import os
                assets_dir = ui.theme.manager.assets_dir
                paths = [
                    os.path.join(assets_dir, "themes", font_file),
                    os.path.join(assets_dir, "fonts", font_file),
                    font_file
                ]
                for path in paths:
                    if os.path.exists(path):
                        try:
                            _fonts[key] = pygame.font.Font(path, size)
                            return _fonts[key]
                        except Exception as e:
                            log.error("Failed to load font %s: %s", path, e)
                log.warning("Could not find custom font '%s' for %s. Falling back to system.", font_file, owner)
        
        # Fallback
        _fonts[key] = pygame.font.SysFont("dejavusansmono", size, bold=True)
    return _fonts[key]


# ---------------------------------------------------------------------------
# Board drawing
# ---------------------------------------------------------------------------

def draw_board(surface: pygame.Surface, gs) -> None:
    """
    Draw the full 8×26 chessboard with:
      - Alternating light/dark squares
      - Restricted-rank overlays (semi-transparent tinted rectangles)
      - Board border
    """
    theme = ui.theme.manager.get_board_dict()
    min_playable = gs.min_playable_rank
    max_playable = gs.max_playable_rank
    cycle = gs.cycle
    
    # Create a temporary surface for the semi-transparent overlays
    overlay_surf = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
    
    # Blinking overlay preparation
    draw_blinking = (cycle % 15 == 0 and cycle <= 45)
    blink_alpha = 0
    if draw_blinking:
        blink_alpha = int(abs(math.sin(pygame.time.get_ticks() / 300.0)) * 70 + 30)

    for rank in range(1, BOARD_RANKS + 1):
        for col in range(1, BOARD_COLS + 1):
            x, y = board_to_pixel(rank, col)
            rect = pygame.Rect(x, y, SQUARE_SIZE, SQUARE_SIZE)

            # Alternating square colour
            if (rank + col) % 2 == 0:
                color = theme["square_light"]
            else:
                color = theme["square_dark"]
            pygame.draw.rect(surface, color, rect)

            # Restricted-rank overlay (Dynamic Bounds)
            if not (min_playable <= rank <= max_playable):
                if rank < min_playable:
                    overlay_color = theme["restricted_low"]
                else:
                    overlay_color = theme["restricted_high"]
                overlay_surf.fill(overlay_color)
                surface.blit(overlay_surf, (x, y))
            elif draw_blinking:
                # Inside playable, but about to shrink -> blinking warning
                if rank in (min_playable, min_playable + 1):
                    # Red for White's side
                    overlay_surf.fill((255, 50, 50, blink_alpha))
                    surface.blit(overlay_surf, (x, y))
                elif rank in (max_playable - 1, max_playable):
                    # Blue for Black's side
                    overlay_surf.fill((50, 100, 255, blink_alpha))
                    surface.blit(overlay_surf, (x, y))

    # Draw board border
    board_rect = pygame.Rect(
        SIDE_LABEL_W,
        PANEL_TOP_H + FILE_LABEL_H,
        BOARD_RANKS * SQUARE_SIZE,
        BOARD_COLS * SQUARE_SIZE,
    )
    pygame.draw.rect(surface, theme["border"], board_rect, 2)


def draw_rank_file_labels(surface: pygame.Surface) -> None:
    """
    Draw rank numbers (1–26) in the left and right gutter,
    and file letters (A–H) in the top and bottom gutter.
    The board is horizontal, so:
      - Rank numbers appear above/below each column of squares
      - File letters appear left/right of each row of squares
    """
    font = _get_font("label", C.FONT_SIZE_LABEL)
    theme = ui.theme.manager.get_board_dict()
    color = theme["label_text"]

    # File letters along LEFT gutter (col 1 = A at top, col 8 = H at bottom)
    file_letters = "ABCDEFGH"
    for col in range(1, BOARD_COLS + 1):
        letter = file_letters[col - 1]
        x_left  = SIDE_LABEL_W // 2
        x_right = SIDE_LABEL_W + BOARD_RANKS * SQUARE_SIZE + SIDE_LABEL_W // 2
        _, y     = board_to_pixel(1, col)
        y_centre = y + SQUARE_SIZE // 2

        # Left gutter
        lbl = font.render(letter, True, color)
        surface.blit(lbl, lbl.get_rect(center=(x_left, y_centre)))
        # Right gutter
        surface.blit(lbl, lbl.get_rect(center=(x_right, y_centre)))

    # Rank numbers along TOP and BOTTOM gutters
    for rank in range(1, BOARD_RANKS + 1):
        x, _ = board_to_pixel(rank, 1)
        x_centre = x + SQUARE_SIZE // 2

        y_top    = PANEL_TOP_H + FILE_LABEL_H // 2
        y_bottom = PANEL_TOP_H + FILE_LABEL_H + BOARD_COLS * SQUARE_SIZE + FILE_LABEL_H // 2

        lbl = font.render(str(rank), True, color)
        surface.blit(lbl, lbl.get_rect(center=(x_centre, y_top)))
        surface.blit(lbl, lbl.get_rect(center=(x_centre, y_bottom)))


# ---------------------------------------------------------------------------
# Piece rendering
# ---------------------------------------------------------------------------




def _piece_display(piece_type: str, owner: str) -> tuple[str, tuple, tuple, tuple | None]:
    """
    Return (display_letter, letter_colour, badge_solid_colour, border_colour_or_None).
    """
    if owner not in ("white", "black", "neutral"):
        owner = "white"
    
    cfg_owner = ui.theme.manager.current_theme["pieces"][owner]
    letter = cfg_owner["chars"].get(piece_type, piece_type)
    return letter, cfg_owner["text"], cfg_owner["badge"], None


def draw_pieces(
    surface: pygame.Surface,
    pieces: list[dict],
) -> None:
    """
    Draw all pieces on the board.

    pieces: list of dicts with keys:
        rank   (int, 1-indexed)
        col    (int, 1-indexed, 1=A … 8=H)
        type   (str, 'P'/'N'/'B'/'R'/'Q'/'K')
        owner  (str, 'white'/'black'/'neutral')

    Renders a PNG sprite when available (assets/pieces/).
    Falls back to the legacy letter+badge rendering if the sprite is missing.
    """
    import assets as _assets_mod
    am = _assets_mod.AssetManager.instance()

    for p in pieces:
        x, y = board_to_pixel(p["rank"], p["col"])
        cx   = x + SQUARE_SIZE // 2
        cy   = y + SQUARE_SIZE // 2

        owner = p["owner"]
        cfg_owner = ui.theme.manager.current_theme["pieces"].get(owner, ui.theme.manager.current_theme["pieces"]["white"])

        letter, lcolor, badge_color, border_color = _piece_display(p["type"], owner)

        # Always draw the badge background so the tile colour is consistent
        badge_rect = pygame.Rect(x + 3, y + 3, SQUARE_SIZE - 6, SQUARE_SIZE - 6)
        pygame.draw.rect(surface, badge_color, badge_rect, border_radius=3)

        if border_color is not None:
            pygame.draw.rect(surface, border_color, badge_rect, width=2, border_radius=3)

        # Try sprite first
        sprite = am.get_piece_sprite(owner, p["type"])
        if sprite is not None:
            # Centre the sprite on the tile with a small inset margin
            margin = 4
            sprite_size = SQUARE_SIZE - margin * 2
            if sprite.get_width() != sprite_size:
                sprite = pygame.transform.smoothscale(sprite, (sprite_size, sprite_size))
            surface.blit(sprite, (x + margin, y + margin))
        else:
            # Fallback: draw letter
            font = _get_font(f"piece_{owner}", cfg_owner["font_size"])
            lbl  = font.render(letter, True, lcolor)
            surface.blit(lbl, lbl.get_rect(center=(cx, cy)))



# ---------------------------------------------------------------------------
# Selection & move highlights
# ---------------------------------------------------------------------------

def draw_highlights(
    surface: pygame.Surface,
    selected_sq: tuple[int, int] | None,
    active_owner: str | None,
    valid_targets: set[tuple[int, int]],
) -> None:
    """
    Draw the selection highlight on a chosen square and dots on valid target squares.

    selected_sq : (rank, col) of the selected piece, or None
    valid_targets : set of (rank, col) that the selected piece can move to
    """
    theme = ui.theme.manager.get_board_dict()
    hl_surf = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)

    if selected_sq:
        rank, col = selected_sq
        x, y = board_to_pixel(rank, col)
        
        if active_owner not in ("white", "black", "neutral"):
            active_owner = "white"
            
        hl_color = ui.theme.manager.current_theme["pieces"][active_owner]["highlight"]
        hl_surf.fill(hl_color)
        surface.blit(hl_surf, (x, y))

    for rank, col in valid_targets:
        x, y = board_to_pixel(rank, col)
        # Draw a smaller dot for valid move targets
        dot_surf = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
        dot_surf.fill((0, 0, 0, 0))
        dot_color = theme["highlight_move"]
        pygame.draw.circle(dot_surf, dot_color,
                           (SQUARE_SIZE // 2, SQUARE_SIZE // 2),
                           SQUARE_SIZE // 5)
        surface.blit(dot_surf, (x, y))



