"""
ui/dialogs.py
=============
Floating UI overlays for King's Trial:
1. Promotion/Demotion Selector – right-click on any owned non-king piece.
2. Respawn Panel – right-click on the King.

Promotion = upgrade to a higher-value type  (spend points, shown in red)
Demotion  = downgrade to a lower-value type (receive refund, shown in green)
Same-type options are omitted from the menu.
"""

import pygame
from constants import (
    SQUARE_SIZE, PIECE_VALUES, PROMOTION_COST,
    PIECE_COLOR_WHITE, GRAYSCALE_UI
)
from ui.renderer import board_to_pixel


def _draw_text(surface, text, font, color, center):
    lbl = font.render(text, True, color)
    rect = lbl.get_rect(center=center)
    surface.blit(lbl, rect)


# ---------------------------------------------------------------------------
# Promotion / Demotion dialog
# ---------------------------------------------------------------------------

import ui.theme

def draw_promotion_dialog(
    surface: pygame.Surface,
    sq: tuple[int, int],
    player_points: int,
    owner: str,
    current_type: str = None,
    piece_counts: dict[str, int] = None,
) -> dict[str, tuple[str, pygame.Rect]]:
    """
    Draw an upgrade / downgrade selector next to the piece at sq.

    Returns
    -------
    dict mapping piece_type -> (action, Rect)
    where action is 'promote' or 'demote'
    """
    rank, col = sq
    bx, by = board_to_pixel(rank, col)

    # Determine the current piece value for split — King/Pawn have no demotion.
    current_val = PIECE_VALUES.get(current_type, 0) if current_type else 0

    all_types = ['Q', 'R', 'B', 'N', 'P']  # excluding K
    entries   = []  # list of (ptype, action, label, colour)

    for ptype in all_types:
        if ptype == current_type:
            continue  # skip self
        pval = PIECE_VALUES.get(ptype, 0)
        
        limit_reached = False
        if piece_counts and ptype in ("N", "B", "R", "Q"):
            from constants import MAX_PIECE_LIMITS
            if piece_counts.get(ptype, 0) >= MAX_PIECE_LIMITS.get(ptype, 99):
                limit_reached = True

        if pval > current_val:
            # Promotion: costs PROMOTION_COST[ptype]
            cost = PROMOTION_COST.get(ptype, 99)
            affordable = player_points >= cost and not limit_reached
            if owner == "white":
                on_col  = (255, 255, 255)
            else:
                on_col  = (230, 210, 160)
                
            if limit_reached:
                label_col = (80, 80, 80)
                cost_str  = "MAXED"
            else:
                label_col = on_col if affordable else (80, 80, 80)
                cost_str  = f"-{cost} pts"
                
            entries.append((ptype, 'promote', f"{ptype}  {cost_str}", label_col))

        elif pval < current_val and current_type not in ("K", "P"):
            # Demotion: refunds raw value difference
            refund    = current_val - pval
            if owner == "white":
                on_col = (160, 230, 160)   # green tint
            else:
                on_col = (120, 200, 120)
            cost_str  = f"+{refund} pts"
            entries.append((ptype, 'demote', f"{ptype}  {cost_str}", on_col))

    if not entries:
        return {}

    item_h = 38
    item_w = 110
    menu_h = len(entries) * item_h

    menu_x = bx + SQUARE_SIZE // 2 - item_w // 2
    menu_y = by - menu_h - 10
    if menu_y < 100:
        menu_y = by + SQUARE_SIZE + 10

    # Draw section labels above each block if both blocks exist
    has_promote = any(e[1] == 'promote' for e in entries)
    has_demote  = any(e[1] == 'demote'  for e in entries)
    hint_h      = 14 if (has_promote and has_demote) else 0

    total_h = menu_h + (hint_h if has_promote else 0) + (hint_h if has_demote else 0)
    bg_rect = pygame.Rect(menu_x, menu_y, item_w, total_h + 4)
    pygame.draw.rect(surface, GRAYSCALE_UI["panel_bg"], bg_rect, border_radius=5)
    pygame.draw.rect(surface, GRAYSCALE_UI["border"], bg_rect, width=2, border_radius=5)

    font_main  = pygame.font.SysFont("dejavusansmono", 16, bold=True)
    font_hint  = pygame.font.SysFont("dejavusansmono", 10)

    import assets as _assets_mod
    am = _assets_mod.AssetManager.instance()

    option_rects: dict[str, tuple[str, pygame.Rect]] = {}
    y = menu_y + 2
    last_action = None

    for ptype, action, label, lcolor in entries:
        # Section header
        if action != last_action and has_promote and has_demote and hint_h:
            title = "▲ UPGRADE" if action == "promote" else "▼ DOWNGRADE"
            t_col = (160, 160, 160)
            _draw_text(surface, title, font_hint, t_col, (menu_x + item_w // 2, y + hint_h // 2))
            y += hint_h
            last_action = action

        rect = pygame.Rect(menu_x + 2, y, item_w - 4, item_h)
        option_rects[ptype] = (action, rect)
        
        mx, my = pygame.mouse.get_pos()
        if rect.collidepoint(mx, my) and lcolor != (80, 80, 80):
            pygame.draw.rect(surface, GRAYSCALE_UI["menu_btn_hover"], rect, border_radius=3)
            
        # Draw sprite icon on the left, cost text on the right
        icon_size = item_h - 8
        sprite = am.get_piece_sprite(owner, ptype)
        if sprite is not None:
            scaled = pygame.transform.smoothscale(sprite, (icon_size, icon_size))
            if lcolor == (80, 80, 80):  # unavailable — dim it
                dimmed = scaled.copy()
                dimmed.fill((0, 0, 0, 160), special_flags=pygame.BLEND_RGBA_MULT)
                scaled = dimmed
            surface.blit(scaled, (rect.x + 2, rect.y + (item_h - icon_size) // 2))
            # Cost text to the right of the icon
            cost_part = label.split("  ", 1)[1] if "  " in label else label
            cost_x = rect.x + icon_size + 6 + (rect.width - icon_size - 6) // 2
            _draw_text(surface, cost_part, font_main, lcolor, (cost_x, y + item_h // 2))
        else:
            _draw_text(surface, label, font_main, lcolor, (menu_x + item_w // 2, y + item_h // 2))

        if (ptype, action, label, lcolor) != entries[-1]:
            pygame.draw.line(
                surface, (60, 60, 60),
                (menu_x + 5, y + item_h), (menu_x + item_w - 5, y + item_h)
            )
        y += item_h

    return option_rects


# ---------------------------------------------------------------------------
# Respawn panel
# ---------------------------------------------------------------------------

def draw_respawn_panel(
    surface: pygame.Surface,
    sq: tuple[int, int],
    player_points: int,
    pool: list[dict],
    owner: str,
    piece_counts: dict[str, int] = None,
) -> list[tuple[dict, pygame.Rect]]:
    """
    Draw a panel showing captured pieces available for respawn.
    Returns a list of (piece_dict, rect) pairs.
    """
    rank, col = sq
    bx, by = board_to_pixel(rank, col)

    # Group pool by type: unique types only, no Kings
    unique_available = []
    seen = set()
    
    # Pawns are always available, overriding pool
    unique_available.append({"type": "P", "owner": owner})
    seen.add("P")
    
    for p in pool:
        if p["type"] != "K" and p["type"] not in seen:
            unique_available.append(p)
            seen.add(p["type"])

    if not unique_available:
        return []

    item_w = 50
    item_h = 50
    cols   = 4
    rows   = (len(unique_available) + cols - 1) // cols
    panel_w = cols * item_w + 10
    panel_h = rows * item_h + 10

    px = bx + SQUARE_SIZE // 2 - panel_w // 2
    py = by - panel_h - 10
    if py < 100:
        py = by + SQUARE_SIZE + 10

    bg_rect = pygame.Rect(px, py, panel_w, panel_h)
    pygame.draw.rect(surface, GRAYSCALE_UI["panel_bg"], bg_rect, border_radius=5)
    pygame.draw.rect(surface, GRAYSCALE_UI["border"], bg_rect, width=2, border_radius=5)

    font_sub = pygame.font.SysFont("dejavusansmono", 10)

    import assets as _assets_mod
    am = _assets_mod.AssetManager.instance()

    clickable = []
    for i, p in enumerate(unique_available):
        ix   = px + 5 + (i % cols) * item_w
        iy   = py + 5 + (i // cols) * item_h
        rect = pygame.Rect(ix, iy, item_w - 5, item_h - 5)

        cost       = PIECE_VALUES[p["type"]]
        
        limit_reached = False
        if piece_counts and p["type"] in ("N", "B", "R", "Q"):
            from constants import MAX_PIECE_LIMITS
            if piece_counts.get(p["type"], 0) >= MAX_PIECE_LIMITS.get(p["type"], 99):
                limit_reached = True

        affordable = player_points >= cost and not limit_reached

        color = (150, 150, 150) if not affordable else ui.theme.manager.get_board_dict()["square_light"]
        pygame.draw.rect(surface, color, rect, border_radius=3)
        
        mx, my = pygame.mouse.get_pos()
        if affordable and rect.collidepoint(mx, my):
            pygame.draw.rect(surface, (255, 255, 255), rect, width=2, border_radius=3)

        from ui.renderer import _piece_display
        letter, lcolor, _, _ = _piece_display(p["type"], owner)
        p_font = pygame.font.SysFont("dejavusansmono", 16, bold=True)

        if not affordable:
            lcolor = (80, 80, 80)

        # Try sprite first; fall back to letter
        sprite = am.get_piece_sprite(owner, p["type"])
        if sprite is not None:
            inner = rect.inflate(-8, -8)
            sprite_size = min(inner.width, inner.height)
            scaled = pygame.transform.smoothscale(sprite, (sprite_size, sprite_size))
            if not affordable:
                dimmed = scaled.copy()
                dimmed.fill((0, 0, 0, 160), special_flags=pygame.BLEND_RGBA_MULT)
                scaled = dimmed
            surface.blit(scaled, scaled.get_rect(center=rect.center))
        else:
            _draw_text(surface, letter, p_font, lcolor, rect.center)

        if limit_reached:
            _draw_text(surface, "MAX", font_sub, lcolor, (rect.right - 8, rect.bottom - 8))
        else:
            _draw_text(surface, f"{cost}",   font_sub, lcolor, (rect.right - 8, rect.bottom - 8))

        clickable.append((p, rect))

    return clickable
